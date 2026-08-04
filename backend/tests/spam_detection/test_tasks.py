import io
import json

import pytest

from spam_detection import artifact_storage, classifier, store
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


def test_generated_artifact_can_be_downloaded(tmp_path, monkeypatch, spam_config, quay_test_db_uri):
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("TESTING", "true")
    (tmp_path / "config.yaml").write_text(
        "is_local: true\n"
        "test_auth: false\n"
        f"DB_URI: {quay_test_db_uri}\n"
        "DB_CONNECTION_ARGS: {}\n"
    )
    from app import app

    config = dict(spam_config)
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


def test_artifact_can_be_promoted_to_fixed_path_with_audit(
    tmp_path, monkeypatch, spam_config, quay_test_db_uri
):
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("TESTING", "true")
    (tmp_path / "config.yaml").write_text(
        "is_local: true\n"
        "test_auth: false\n"
        f"DB_URI: {quay_test_db_uri}\n"
        "DB_CONNECTION_ARGS: {}\n"
    )
    from app import app

    config = dict(spam_config)
    app.config.update(config)
    created = store.create_classifier(config, {"name": "promote", "enabled": True})
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
    trained = classifier.train_classifier(config, created["uuid"], artifact_version="promote-v1")

    response = app.test_client().post(
        f"/spam-detection/classifiers/{created['uuid']}/promote-artifact"
    )

    assert response.status_code == 200
    body = json.loads(response.data)
    storage = artifact_storage.get_artifact_storage(config)
    promoted_path = storage.promoted_uri()
    assert body["promoted_path"] == promoted_path
    assert body["promoted_sha256"] == trained["artifact_sha256"]
    assert body["promoted_checksum_path"] == f"{promoted_path}.sha256"
    assert storage.read(promoted_path) == storage.read(trained["artifact_path"])
    assert storage.exists(f"{promoted_path}.sha256")
    build_output = tmp_path / "quay-build" / "conf" / "spam-detection" / "classifier.json"
    materialized = classifier.materialize_promoted_artifact(config, str(build_output))
    assert materialized["artifact_version"] == "promote-v1"
    assert materialized["sha256"] == trained["artifact_sha256"]
    assert build_output.read_bytes() == storage.read(promoted_path)
    assert build_output.with_suffix(".json.sha256").read_text().startswith(
        trained["artifact_sha256"]
    )
    action = next(
        item for item in store.list_audit_actions(config) if item["action"] == "artifact_promote"
    )
    assert action["details_json"] == {
        "classifier_uuid": created["uuid"],
        "artifact_version": "promote-v1",
        "artifact_sha256": trained["artifact_sha256"],
        "destination": promoted_path,
        "checksum_destination": f"{promoted_path}.sha256",
    }


def test_artifact_can_be_imported_activated_and_downloaded(
    tmp_path, monkeypatch, spam_config, quay_test_db_uri
):
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("TESTING", "true")
    (tmp_path / "config.yaml").write_text(
        "is_local: true\n"
        "test_auth: false\n"
        f"DB_URI: {quay_test_db_uri}\n"
        "DB_CONNECTION_ARGS: {}\n"
    )
    from app import app

    app.config.update(spam_config)
    artifact = {
        "version": "uploaded-v1",
        "training_corpus_version": "seed-2",
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
        "training_metrics": {
            "example_count": 2,
            "spam_examples": 1,
            "ham_examples": 1,
        },
    }
    artifact_bytes = json.dumps(artifact).encode("utf-8")

    response = app.test_client().post(
        "/spam-detection/classifiers/import-artifact",
        data={
            "name": "Uploaded classifier",
            "enabled": "true",
            "artifact": (io.BytesIO(artifact_bytes), "classifier.json"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    imported = json.loads(response.data)["classifier"]
    assert imported["enabled"] == 1
    assert imported["base_artifact_path"] == imported["artifact_path"]
    download = app.test_client().get(
        f"/spam-detection/classifiers/{imported['uuid']}/artifact"
    )
    assert download.status_code == 200
    assert download.data == artifact_bytes
