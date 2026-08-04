import os
import sys
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest


BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


STATE_DB_URI = os.environ.get("SPAM_DETECTION_TEST_STATE_DB_URI")
S3_ENDPOINT = os.environ.get("SPAM_DETECTION_TEST_S3_ENDPOINT_URL")


def _require_storage_config():
    if not STATE_DB_URI or not S3_ENDPOINT:
        pytest.fail(
            "spam tests require PostgreSQL and MinIO; run `make spam-storage-test` "
            "from the repository root"
        )


def _clear_s3(config):
    from spam_detection import artifact_storage

    storage = artifact_storage.get_artifact_storage(config)
    bucket = config["SPAM_DETECTION_S3_BUCKET"]
    prefix = f"{config['SPAM_DETECTION_S3_PREFIX'].strip('/')}/"
    listed = storage.client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    objects = [{"Key": item["Key"]} for item in listed.get("Contents", [])]
    if objects:
        storage.client.delete_objects(Bucket=bucket, Delete={"Objects": objects})


@pytest.fixture(scope="session")
def quay_test_db_uri():
    _require_storage_config()
    import psycopg2
    from psycopg2 import sql

    database_name = f"quay_test_{uuid.uuid4().hex}"
    parsed = urlsplit(STATE_DB_URI)
    test_uri = urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{database_name}", parsed.query, parsed.fragment)
    )
    connection = psycopg2.connect(STATE_DB_URI)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    connection.close()

    yield test_uri

    connection = psycopg2.connect(STATE_DB_URI)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (database_name,),
        )
        cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
    connection.close()


@pytest.fixture(scope="session")
def spam_test_config():
    _require_storage_config()
    suffix = uuid.uuid4().hex
    config = {
        "SPAM_DETECTION_STATE_DB_URI": STATE_DB_URI,
        "SPAM_DETECTION_STATE_DB_SCHEMA": f"spam_test_{suffix}",
        "SPAM_DETECTION_STATE_DB_CREATE_SCHEMA": True,
        "SPAM_DETECTION_STATE_DB_POOL_MAX": 12,
        "SPAM_DETECTION_STATE_DB_LOCK_CONNECTIONS": 2,
        "SPAM_DETECTION_S3_ENDPOINT_URL": S3_ENDPOINT,
        "SPAM_DETECTION_S3_BUCKET": os.environ.get(
            "SPAM_DETECTION_TEST_S3_BUCKET", "quay-service-tool-tests"
        ),
        "SPAM_DETECTION_S3_PREFIX": f"tests/{suffix}",
        "SPAM_DETECTION_S3_REGION": "us-east-1",
        "SPAM_DETECTION_S3_ADDRESSING_STYLE": "path",
        "SPAM_DETECTION_S3_VERIFY_TLS": False,
        "SPAM_DETECTION_S3_CREATE_BUCKET": True,
        "SPAM_DETECTION_MIN_SPAM_EXAMPLES": 1,
        "SPAM_DETECTION_MIN_HAM_EXAMPLES": 1,
    }

    from spam_detection import database

    database.initialize_state_db(config)
    yield config

    import psycopg2
    from psycopg2 import sql

    _clear_s3(config)
    with psycopg2.connect(STATE_DB_URI) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(config["SPAM_DETECTION_STATE_DB_SCHEMA"])
                )
            )


@pytest.fixture
def spam_config(spam_test_config):
    from spam_detection.database import connect_state_db

    with connect_state_db(spam_test_config) as connection:
        connection.execute(
            """
            TRUNCATE TABLE
                spam_action_history,
                spam_scan_match,
                spam_quarantine_record,
                spam_scan_run,
                spam_training_example,
                spam_policy,
                spam_classifier
            RESTART IDENTITY CASCADE
            """
        )
    _clear_s3(spam_test_config)
    yield dict(spam_test_config)
