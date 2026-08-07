import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from spam_detection import artifact_storage, classifier, store


def _artifact(version):
    return {
        "version": version,
        "training_corpus_version": "integration-seed",
        "spam_prior": 0.5,
        "ham_prior": 0.5,
        "token_spam_counts": {"casino": 2},
        "token_ham_counts": {"container": 2},
        "spam_token_total": 2,
        "ham_token_total": 2,
        "vocabulary_size": 2,
        "smoothing": 1.0,
        "ingress_threshold": 0.9,
        "ingress_thresholds": {"public": 0.9, "private": 0.98},
        "feature_config": {
            "token_pattern": classifier.DEFAULT_TOKEN_PATTERN,
            "include_repository_name": False,
        },
        "training_metrics": {
            "example_count": 2,
            "spam_examples": 1,
            "ham_examples": 1,
            "validation_status": "not_available",
        },
    }


def test_postgres_state_and_s3_artifacts_are_shared_across_workers(
    spam_config, tmp_path
):
    shared_config = spam_config
    artifact = _artifact(f"integration-{uuid.uuid4().hex}")
    content = json.dumps(artifact, indent=2).encode("utf-8")

    def import_from_worker(index):
        return classifier.import_classifier_artifact(
            dict(shared_config),
            f"worker-{index}",
            content,
            enabled=True,
            operator=f"worker-{index}",
        )

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(import_from_worker, range(3)))

    assert sum(1 for _, created in results if created) == 1
    imported = results[0][0]
    persisted = store.get_classifier(dict(shared_config), imported["uuid"])
    assert persisted["artifact_path"].startswith("s3://")
    assert classifier.load_artifact_from_classifier(shared_config, persisted) == artifact

    storage = artifact_storage.get_artifact_storage(shared_config)
    assert storage.exists(persisted["artifact_path"])
    assert storage.read(persisted["artifact_path"]) == content

    store.add_training_example(
        shared_config,
        persisted["uuid"],
        {"text": "casino jackpot", "label": "spam"},
    )
    store.add_training_example(
        dict(shared_config),
        persisted["uuid"],
        {"text": "container documentation", "label": "ham"},
    )
    trained = classifier.train_classifier(
        shared_config,
        persisted["uuid"],
        artifact_version=f"trained-{uuid.uuid4().hex}",
    )
    assert trained["base_artifact_path"] == persisted["base_artifact_path"]
    trained_model = classifier.load_artifact_from_classifier(shared_config, trained)
    assert trained_model["training_metrics"]["example_count"] == 4
    promoted = classifier.promote_artifact(dict(shared_config), trained["uuid"])
    assert promoted["promoted_path"].startswith("s3://")
    assert storage.read(promoted["promoted_path"]) == storage.read(trained["artifact_path"])
    assert storage.read(promoted["promoted_checksum_path"]).decode("utf-8") == (
        f"{trained['artifact_sha256']}  classifier.json\n"
    )
    build_output = tmp_path / "quay-build" / "conf" / "spam-detection" / "classifier.json"
    materialized = classifier.materialize_promoted_artifact(
        dict(shared_config), str(build_output)
    )
    assert materialized["artifact_version"] == trained["artifact_version"]
    assert materialized["sha256"] == trained["artifact_sha256"]
    assert build_output.read_bytes() == storage.read(trained["artifact_path"])
    assert build_output.with_suffix(".json.sha256").read_text() == (
        f"{trained['artifact_sha256']}  classifier.json\n"
    )

    first_run = store.create_scan_run(shared_config, "integration", True, {}, {})
    with pytest.raises(ValueError, match="already running"):
        store.create_scan_run(dict(shared_config), "other-worker", True, {}, {})
    assert store.update_scan_run(
        shared_config, first_run["id"], status="completed"
    )


def test_immutable_artifact_writes_do_not_overwrite_across_workers(
    spam_config, monkeypatch
):
    storage = artifact_storage.get_artifact_storage(spam_config)
    version = f"immutable-{uuid.uuid4().hex}"
    uri = storage.classifier_uri(version)
    contents = [b'{"worker": 1}', b'{"worker": 2}']
    original_head = storage.client.head_object
    first_missing_heads = 0
    head_lock = threading.Lock()
    both_checked = threading.Barrier(2)

    def racing_head(**kwargs):
        nonlocal first_missing_heads
        try:
            return original_head(**kwargs)
        except storage._client_error as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            should_wait = False
            if kwargs.get("Key") == storage._location(uri)[1] and status == 404:
                with head_lock:
                    if first_missing_heads < 2:
                        first_missing_heads += 1
                        should_wait = True
            if should_wait:
                both_checked.wait(timeout=5)
            raise

    monkeypatch.setattr(storage.client, "head_object", racing_head)

    def write(content):
        try:
            storage.put_classifier(version, content)
            return "written"
        except artifact_storage.ArtifactStorageError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(write, contents))

    assert sorted(results) == ["rejected", "written"]
    assert storage.read(uri) in contents


def test_classifier_promotion_is_serialized_across_workers(
    spam_config, monkeypatch
):
    config = dict(spam_config)

    def trained_classifier(name, version):
        created = store.create_classifier(config, {"name": name})
        store.add_training_example(
            config, created["uuid"], {"text": f"casino {name}", "label": "spam"}
        )
        store.add_training_example(
            config, created["uuid"], {"text": f"container {name}", "label": "ham"}
        )
        return classifier.train_classifier(config, created["uuid"], artifact_version=version)

    classifiers = [
        trained_classifier("first", f"promote-first-{uuid.uuid4().hex}"),
        trained_classifier("second", f"promote-second-{uuid.uuid4().hex}"),
    ]
    original_promote = artifact_storage.S3ArtifactStorage.promote
    counter_lock = threading.Lock()
    active_promotions = 0
    maximum_active_promotions = 0

    def observed_promote(self, content):
        nonlocal active_promotions, maximum_active_promotions
        with counter_lock:
            active_promotions += 1
            maximum_active_promotions = max(maximum_active_promotions, active_promotions)
        try:
            time.sleep(0.1)
            return original_promote(self, content)
        finally:
            with counter_lock:
                active_promotions -= 1

    monkeypatch.setattr(artifact_storage.S3ArtifactStorage, "promote", observed_promote)
    start = threading.Barrier(2)

    def promote(configured):
        start.wait(timeout=5)
        return classifier.promote_artifact(dict(config), configured["uuid"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(promote, classifiers))

    assert maximum_active_promotions == 1
    storage = artifact_storage.get_artifact_storage(config)
    promoted_content = storage.read(storage.promoted_uri())
    checksum = storage.read(f"{storage.promoted_uri()}.sha256").decode("utf-8")
    promoted_sha256 = hashlib.sha256(promoted_content).hexdigest()
    assert promoted_sha256 in [result["promoted_sha256"] for result in results]
    assert checksum == f"{promoted_sha256}  classifier.json\n"
    assert promoted_content in [
        storage.read(configured["artifact_path"]) for configured in classifiers
    ]


def test_classifier_activation_is_serialized_across_workers(spam_config):
    config = dict(spam_config)
    start = threading.Barrier(2)

    def create_active(name):
        start.wait(timeout=5)
        return store.create_classifier(config, {"name": name, "enabled": True})

    with ThreadPoolExecutor(max_workers=2) as executor:
        created = list(executor.map(create_active, ["first", "second"]))

    classifiers = store.list_classifiers(config)
    enabled = [configured for configured in classifiers if configured["enabled"]]
    assert len(created) == 2
    assert len(enabled) == 1
    assert store.get_policy(config)["active_classifier_id"] == enabled[0]["id"]


def test_policy_activation_updates_enabled_classifier(spam_config):
    config = dict(spam_config)
    first = store.create_classifier(config, {"name": "first", "enabled": True})
    second = store.create_classifier(config, {"name": "second"})

    store.update_policy(config, {"active_classifier_uuid": second["uuid"]})

    assert store.get_classifier(config, first["uuid"])["enabled"] == 0
    assert store.get_classifier(config, second["uuid"])["enabled"] == 1
