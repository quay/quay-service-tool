import hashlib
import json

import pytest

from spam_detection import classifier, store


def _config(tmp_path):
    return {
        "SPAM_DETECTION_STATE_DB_URI": f"sqlite:///{tmp_path / 'state.db'}",
        "SPAM_DETECTION_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "SPAM_DETECTION_MIN_SPAM_EXAMPLES": 1,
        "SPAM_DETECTION_MIN_HAM_EXAMPLES": 1,
    }


def _add_examples(config, classifier_uuid, spam=1, ham=1):
    for index in range(spam):
        store.add_training_example(
            config,
            classifier_uuid,
            {"text": f"casino bonus jackpot {index}", "label": "spam"},
        )
    for index in range(ham):
        store.add_training_example(
            config,
            classifier_uuid,
            {"text": f"container image documentation {index}", "label": "ham"},
        )


def _artifact(version="import-v1"):
    return {
        "version": version,
        "training_corpus_version": "seed-2",
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


def test_import_preserves_artifact_and_activates_classifier(tmp_path):
    config = _config(tmp_path)
    artifact_bytes = json.dumps(_artifact(), indent=2).encode("utf-8")

    imported, created = classifier.import_classifier_artifact(
        config,
        "Imported classifier",
        artifact_bytes,
        enabled=True,
        operator="tester",
    )

    assert created
    assert imported["enabled"] == 1
    assert imported["artifact_version"] == "import-v1"
    assert imported["base_model_snapshot_json"]["version"] == "import-v1"
    assert store.get_policy(config)["active_classifier_id"] == imported["id"]
    with open(imported["artifact_path"], "rb") as artifact_file:
        assert artifact_file.read() == artifact_bytes
    assert imported["artifact_sha256"] == hashlib.sha256(artifact_bytes).hexdigest()


def test_import_is_idempotent_for_same_version_and_content(tmp_path):
    config = _config(tmp_path)
    artifact_bytes = json.dumps(_artifact()).encode("utf-8")
    first, first_created = classifier.import_classifier_artifact(
        config, "Imported classifier", artifact_bytes
    )
    second, second_created = classifier.import_classifier_artifact(
        config, "Imported classifier", artifact_bytes, enabled=True
    )

    assert first_created
    assert not second_created
    assert second["uuid"] == first["uuid"]
    assert second["enabled"] == 1
    assert len(store.list_classifiers(config)) == 1


def test_import_is_idempotent_after_classifier_is_retrained(tmp_path):
    config = _config(tmp_path)
    artifact_bytes = json.dumps(_artifact()).encode("utf-8")
    first, _ = classifier.import_classifier_artifact(
        config, "Imported classifier", artifact_bytes, enabled=True
    )
    store.add_training_example(
        config, first["uuid"], {"text": "casino jackpot", "label": "spam"}
    )
    classifier.train_classifier(config, first["uuid"], artifact_version="import-v2")

    second, created = classifier.import_classifier_artifact(
        config, "Imported classifier", artifact_bytes, enabled=True
    )

    assert not created
    assert second["uuid"] == first["uuid"]
    assert second["artifact_version"] == "import-v2"
    assert second["base_artifact_version"] == "import-v1"
    assert len(store.list_classifiers(config)) == 1


def test_import_rejects_same_version_with_different_content(tmp_path):
    config = _config(tmp_path)
    first = json.dumps(_artifact()).encode("utf-8")
    changed = _artifact()
    changed["token_spam_counts"]["casino"] = 3
    second = json.dumps(changed).encode("utf-8")
    classifier.import_classifier_artifact(config, "Imported classifier", first)

    with pytest.raises(classifier.ClassifierError, match="different content"):
        classifier.import_classifier_artifact(config, "Changed classifier", second)


def test_retraining_imported_classifier_combines_base_with_feedback_once(tmp_path):
    config = _config(tmp_path)
    imported, _ = classifier.import_classifier_artifact(
        config,
        "Imported classifier",
        json.dumps(_artifact()).encode("utf-8"),
        enabled=True,
    )
    store.add_training_example(
        config,
        imported["uuid"],
        {"text": "casino jackpot", "label": "spam"},
    )
    store.add_training_example(
        config,
        imported["uuid"],
        {"text": "container documentation", "label": "ham"},
    )

    first = classifier.train_classifier(config, imported["uuid"], artifact_version="import-v2")
    second = classifier.train_classifier(config, imported["uuid"], artifact_version="import-v3")

    for trained in (first, second):
        model = trained["model_snapshot_json"]
        assert model["token_spam_counts"]["casino"] == 3
        assert model["token_ham_counts"]["container"] == 3
        assert model["training_metrics"]["spam_examples"] == 2
        assert model["training_metrics"]["ham_examples"] == 2
        assert model["training_corpus_version"].startswith("seed-2+")
def test_training_writes_quay_compatible_artifact_and_sha(tmp_path):
    config = _config(tmp_path)
    created = store.create_classifier(config, {"name": "test", "enabled": True})
    _add_examples(config, created["uuid"])

    trained = classifier.train_classifier(config, created["uuid"], artifact_version="test-v1")

    with open(trained["artifact_path"], "rb") as artifact_file:
        artifact_bytes = artifact_file.read()
    artifact = json.loads(artifact_bytes.decode("utf-8"))

    assert trained["artifact_sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert artifact["version"] == "test-v1"
    assert artifact["token_spam_counts"]["casino"] == 1
    assert artifact["token_ham_counts"]["container"] == 1
    assert artifact["feature_config"]["token_pattern"] == classifier.DEFAULT_TOKEN_PATTERN
    assert "ingress_threshold" in artifact
    assert artifact["training_metrics"]["example_count"] == 2
    assert artifact["training_metrics"]["spam_examples"] == 1
    assert artifact["training_metrics"]["ham_examples"] == 1
    assert classifier.classify_text(artifact, "casino bonus")["score"] > 0.5


def test_training_rejects_corpus_below_minimum_label_counts(tmp_path):
    config = _config(tmp_path)
    config["SPAM_DETECTION_MIN_SPAM_EXAMPLES"] = 2
    config["SPAM_DETECTION_MIN_HAM_EXAMPLES"] = 2
    created = store.create_classifier(config, {"name": "test", "enabled": True})
    _add_examples(config, created["uuid"], spam=1, ham=2)

    with pytest.raises(classifier.ClassifierError, match="at least 2 spam examples"):
        classifier.train_classifier(config, created["uuid"], artifact_version="test-v1")


def test_training_uses_active_policy_ingress_threshold(tmp_path):
    config = _config(tmp_path)
    created = store.create_classifier(config, {"name": "test", "enabled": True})
    store.update_policy(config, {"ingress_threshold": 0.82})
    _add_examples(config, created["uuid"])

    trained = classifier.train_classifier(config, created["uuid"], artifact_version="test-v1")

    with open(trained["artifact_path"], encoding="utf-8") as artifact_file:
        artifact = json.load(artifact_file)
    assert artifact["ingress_threshold"] == 0.82
    assert artifact["ingress_thresholds"]["public"] == 0.82
    assert artifact["ingress_thresholds"]["private"] == 0.98


def test_export_refreshes_active_policy_ingress_threshold(tmp_path):
    config = _config(tmp_path)
    created = store.create_classifier(config, {"name": "test", "enabled": True})
    _add_examples(config, created["uuid"])
    trained = classifier.train_classifier(config, created["uuid"], artifact_version="test-v1")

    store.update_policy(config, {"ingress_threshold": 0.75})
    exported = classifier.export_artifact(config, created["uuid"])

    with open(exported["artifact_path"], encoding="utf-8") as artifact_file:
        artifact = json.load(artifact_file)
    assert exported["artifact_version"] != trained["artifact_version"]
    assert artifact["ingress_threshold"] == 0.75
    assert artifact["ingress_thresholds"]["public"] == 0.75
    assert artifact["ingress_thresholds"]["private"] == 0.98


def test_export_writes_build_artifact_copy(tmp_path):
    config = _config(tmp_path)
    created = store.create_classifier(config, {"name": "test", "enabled": True})
    _add_examples(config, created["uuid"])
    classifier.train_classifier(config, created["uuid"], artifact_version="test-v1")
    output_path = tmp_path / "quay-build" / "spam-classifier.json"

    exported = classifier.export_artifact(config, created["uuid"], output_path=str(output_path))

    assert exported["artifact_path"] != exported["export_path"]
    assert exported["export_path"] == str(output_path)
    with open(exported["artifact_path"], "rb") as managed_file:
        managed_bytes = managed_file.read()
    with open(output_path, "rb") as exported_file:
        exported_bytes = exported_file.read()
    assert exported_bytes == managed_bytes
    assert exported["export_sha256"] == hashlib.sha256(exported_bytes).hexdigest()
    assert output_path.with_suffix(".json.sha256").exists()


def test_export_rejects_artifact_without_training_metrics(tmp_path):
    config = _config(tmp_path)
    created = store.create_classifier(config, {"name": "test", "enabled": True})
    artifact = {
        "version": "legacy-v1",
        "spam_prior": 0.5,
        "ham_prior": 0.5,
        "token_spam_counts": {"casino": 1},
        "token_ham_counts": {"container": 1},
        "spam_token_total": 1,
        "ham_token_total": 1,
        "vocabulary_size": 2,
        "smoothing": 1.0,
        "ingress_threshold": 0.9,
        "ingress_thresholds": {"public": 0.9, "private": 0.98},
        "feature_config": {
            "token_pattern": classifier.DEFAULT_TOKEN_PATTERN,
            "include_repository_name": False,
        },
        "training_corpus_version": "legacy",
    }
    path, sha256 = classifier.write_artifact(config, artifact)
    store.update_classifier_artifact(config, created["id"], artifact, path, sha256)

    with pytest.raises(classifier.ClassifierError, match="missing training metrics"):
        classifier.export_artifact(config, created["uuid"], artifact_version="legacy-v2")


def test_custom_token_pattern_is_rejected(tmp_path):
    config = _config(tmp_path)
    with pytest.raises(ValueError):
        store.create_classifier(
            config,
            {
                "name": "test",
                "feature_config": {
                    "token_pattern": "(a+)+",
                    "include_repository_name": False,
                },
            },
        )


def test_duplicate_artifact_version_is_rejected_before_overwrite(tmp_path):
    config = _config(tmp_path)
    first = store.create_classifier(config, {"name": "first", "enabled": True})
    second = store.create_classifier(config, {"name": "second"})
    for created in [first, second]:
        _add_examples(config, created["uuid"])

    classifier.train_classifier(config, first["uuid"], artifact_version="test-v1")

    with pytest.raises(classifier.ClassifierError):
        classifier.train_classifier(config, second["uuid"], artifact_version="test-v1")
