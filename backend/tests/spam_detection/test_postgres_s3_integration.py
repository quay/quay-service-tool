import json
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
