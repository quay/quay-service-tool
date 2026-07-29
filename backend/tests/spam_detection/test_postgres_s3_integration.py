import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from spam_detection import artifact_storage, classifier, store


STATE_DB_URI = os.environ.get("SPAM_DETECTION_INTEGRATION_STATE_DB_URI")
S3_ENDPOINT = os.environ.get("SPAM_DETECTION_INTEGRATION_S3_ENDPOINT_URL")

pytestmark = pytest.mark.skipif(
    not STATE_DB_URI or not S3_ENDPOINT,
    reason="local PostgreSQL/S3 integration services are not configured",
)


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


@pytest.fixture
def shared_config():
    suffix = uuid.uuid4().hex
    schema = f"spam_test_{suffix}"
    prefix = f"integration-tests/{suffix}"
    config = {
        "SPAM_DETECTION_STATE_DB_URI": STATE_DB_URI,
        "SPAM_DETECTION_STATE_DB_SCHEMA": schema,
        "SPAM_DETECTION_STATE_DB_CREATE_SCHEMA": True,
        "SPAM_DETECTION_STATE_DB_POOL_MAX": 12,
        "SPAM_DETECTION_ARTIFACT_STORAGE": "s3",
        "SPAM_DETECTION_S3_ENDPOINT_URL": S3_ENDPOINT,
        "SPAM_DETECTION_S3_BUCKET": os.environ.get(
            "SPAM_DETECTION_INTEGRATION_S3_BUCKET", "quay-service-tool-tests"
        ),
        "SPAM_DETECTION_S3_PREFIX": prefix,
        "SPAM_DETECTION_S3_REGION": "us-east-1",
        "SPAM_DETECTION_S3_ADDRESSING_STYLE": "path",
        "SPAM_DETECTION_S3_VERIFY_TLS": False,
        "SPAM_DETECTION_S3_CREATE_BUCKET": True,
        "SPAM_DETECTION_MIN_SPAM_EXAMPLES": 1,
        "SPAM_DETECTION_MIN_HAM_EXAMPLES": 1,
    }
    yield config

    import boto3
    import psycopg2
    from botocore.config import Config
    from psycopg2 import sql

    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )
    listed = s3.list_objects_v2(
        Bucket=config["SPAM_DETECTION_S3_BUCKET"], Prefix=f"{prefix}/"
    )
    objects = [{"Key": item["Key"]} for item in listed.get("Contents", [])]
    if objects:
        s3.delete_objects(
            Bucket=config["SPAM_DETECTION_S3_BUCKET"], Delete={"Objects": objects}
        )

    with psycopg2.connect(STATE_DB_URI) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


def test_postgres_state_and_s3_artifacts_are_shared_across_workers(shared_config):
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
    assert persisted["model_snapshot_json"] is None
    assert persisted["base_model_snapshot_json"] is None
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
    assert trained["model_snapshot_json"] is None
    assert trained["base_artifact_path"] == persisted["base_artifact_path"]
    trained_model = classifier.load_artifact_from_classifier(shared_config, trained)
    assert trained_model["training_metrics"]["example_count"] == 4
    promoted = classifier.promote_artifact(dict(shared_config), trained["uuid"])
    assert promoted["promoted_path"].startswith("s3://")
    assert storage.read(promoted["promoted_path"]) == storage.read(trained["artifact_path"])

    first_run = store.create_scan_run(shared_config, "integration", True, {}, {})
    with pytest.raises(ValueError, match="already running"):
        store.create_scan_run(dict(shared_config), "other-worker", True, {}, {})
    assert store.update_scan_run(
        shared_config, first_run["id"], status="completed"
    )
