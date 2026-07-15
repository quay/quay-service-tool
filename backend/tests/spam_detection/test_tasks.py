import pytest

from spam_detection import classifier, store
from tasks.spam_detection import _scan_limit


@pytest.mark.parametrize("value", [0, "0", "all", "unbounded"])
def test_scan_limit_supports_unbounded(value):
    assert _scan_limit(value, 100, 10000) == 0


def test_scan_limit_defaults_to_unbounded():
    assert _scan_limit(None, 0, 10000) == 0


def test_scan_limit_still_bounds_positive_values():
    assert _scan_limit(500, 0, 10000) == 500
    with pytest.raises(ValueError, match="or 0 for all"):
        _scan_limit(10001, 0, 10000)


def test_generated_artifact_can_be_downloaded(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("TESTING", "true")
    (tmp_path / "config.yaml").write_text(
        "is_local: true\n"
        "test_auth: false\n"
        f"DB_URI: sqlite:///{tmp_path / 'quay.db'}\n"
        "DB_CONNECTION_ARGS: {}\n"
    )
    from app import app

    config = {
        "SPAM_DETECTION_STATE_DB_URI": f"sqlite:///{tmp_path / 'state.db'}",
        "SPAM_DETECTION_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "SPAM_DETECTION_MIN_SPAM_EXAMPLES": 1,
        "SPAM_DETECTION_MIN_HAM_EXAMPLES": 1,
    }
    app.config.update(config)
    created = store.create_classifier(config, {"name": "download", "enabled": True})
    store.add_training_example(
        config,
        created["uuid"],
        {"text": "casino https://spam.example", "label": "spam"},
    )
    store.add_training_example(
        config,
        created["uuid"],
        {"text": "container documentation", "label": "ham"},
    )
    classifier.train_classifier(config, created["uuid"], artifact_version="download-v1")

    response = app.test_client().get(
        f"/spam-detection/classifiers/{created['uuid']}/artifact"
    )

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.headers["Content-Disposition"].endswith(
        'filename=quay-spam-classifier-download-v1.json'
    )
    assert response.json["version"] == "download-v1"
