import hashlib
import json

import pytest

from spam_detection import classifier, store


def _config(tmp_path):
    return {
        "SPAM_DETECTION_STATE_DB_URI": f"sqlite:///{tmp_path / 'state.db'}",
        "SPAM_DETECTION_ARTIFACT_DIR": str(tmp_path / "artifacts"),
    }


def test_training_writes_quay_compatible_artifact_and_sha(tmp_path):
    config = _config(tmp_path)
    created = store.create_classifier(config, {"name": "test", "enabled": True})
    store.add_training_example(
        config,
        created["uuid"],
        {"text": "casino bonus jackpot", "label": "spam"},
    )
    store.add_training_example(
        config,
        created["uuid"],
        {"text": "container image documentation", "label": "ham"},
    )

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
    assert classifier.classify_text(artifact, "casino bonus")["score"] > 0.5


def test_training_uses_active_policy_ingress_threshold(tmp_path):
    config = _config(tmp_path)
    created = store.create_classifier(config, {"name": "test", "enabled": True})
    store.update_policy(config, {"ingress_threshold": 0.82})
    store.add_training_example(config, created["uuid"], {"text": "casino bonus", "label": "spam"})
    store.add_training_example(config, created["uuid"], {"text": "container image", "label": "ham"})

    trained = classifier.train_classifier(config, created["uuid"], artifact_version="test-v1")

    with open(trained["artifact_path"], encoding="utf-8") as artifact_file:
        artifact = json.load(artifact_file)
    assert artifact["ingress_threshold"] == 0.82
    assert artifact["ingress_thresholds"]["public"] == 0.82
    assert artifact["ingress_thresholds"]["private"] == 0.98


def test_export_refreshes_active_policy_ingress_threshold(tmp_path):
    config = _config(tmp_path)
    created = store.create_classifier(config, {"name": "test", "enabled": True})
    store.add_training_example(config, created["uuid"], {"text": "casino bonus", "label": "spam"})
    store.add_training_example(config, created["uuid"], {"text": "container image", "label": "ham"})
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
    store.add_training_example(config, created["uuid"], {"text": "casino bonus", "label": "spam"})
    store.add_training_example(config, created["uuid"], {"text": "container image", "label": "ham"})
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
        store.add_training_example(config, created["uuid"], {"text": "casino bonus", "label": "spam"})
        store.add_training_example(config, created["uuid"], {"text": "container image", "label": "ham"})

    classifier.train_classifier(config, first["uuid"], artifact_version="test-v1")

    with pytest.raises(classifier.ClassifierError):
        classifier.train_classifier(config, second["uuid"], artifact_version="test-v1")
