import hashlib
import json

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
