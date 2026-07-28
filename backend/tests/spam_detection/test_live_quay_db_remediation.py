import os
from uuid import uuid4

import pytest

from spam_detection import classifier, quay_db, remediation, scanner, store
from spam_detection.database import connect_state_db


pytestmark = pytest.mark.skipif(
    not os.environ.get("SPAM_DETECTION_LIVE_QUAY_DB_URI"),
    reason="set SPAM_DETECTION_LIVE_QUAY_DB_URI to run live Quay DB remediation coverage",
)


SPAM_DESCRIPTION = "free casino bonus crypto gift cards click now"
HAM_DESCRIPTION = "trusted base image for python applications"
QUARANTINE_DESCRIPTION = "quarantined by live spam remediation test"
REDACTED_DESCRIPTION = "[redacted by live spam remediation test]"


def _config(tmp_path):
    live_db_uri = os.environ["SPAM_DETECTION_LIVE_QUAY_DB_URI"]
    return {
        "SPAM_DETECTION_STATE_DB_URI": f"sqlite:///{tmp_path / 'state.db'}",
        "SPAM_DETECTION_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "SPAM_DETECTION_READONLY_DB_URI": os.environ.get(
            "SPAM_DETECTION_LIVE_QUAY_READONLY_DB_URI", live_db_uri
        ),
        "SPAM_DETECTION_WRITE_DB_URI": os.environ.get(
            "SPAM_DETECTION_LIVE_QUAY_WRITE_DB_URI", live_db_uri
        ),
        "SPAM_DETECTION_SLEEP_BETWEEN_BATCHES": 0,
        "SPAM_DETECTION_BATCH_SIZE": 200,
        "SPAM_DETECTION_MIN_SPAM_EXAMPLES": 1,
        "SPAM_DETECTION_MIN_HAM_EXAMPLES": 1,
    }


def _param(db):
    return db.param


def _fetch_visibility_id(db, name):
    cursor = db.execute_sql(f'SELECT id FROM "visibility" WHERE name = {_param(db)}', (name,))
    row = cursor.fetchone()
    assert row is not None, f"missing Quay visibility row {name!r}"
    return row[0]


def _seed_namespace_and_repos(config):
    suffix = uuid4().hex[:12]
    namespace = f"spam-live-{suffix}"
    spam_repo = f"spam-{suffix}"
    restore_repo = f"restore-{suffix}"
    ham_repo = f"ham-{suffix}"
    private_repo = f"private-{suffix}"

    with quay_db.write_db(config) as db:
        public_visibility_id = _fetch_visibility_id(db, "public")
        private_visibility_id = _fetch_visibility_id(db, "private")
        cursor = db.execute_sql(
            f"""
            INSERT INTO "user" (
                uuid, username, email, verified, organization, robot,
                invoice_email, last_invalid_login, creation_date
            ) VALUES (
                {_param(db)}, {_param(db)}, {_param(db)}, {_param(db)}, {_param(db)},
                {_param(db)}, {_param(db)}, NOW(), NOW()
            )
            RETURNING id
            """,
            (
                str(uuid4()),
                namespace,
                f"{namespace}@example.com",
                True,
                False,
                False,
                False,
            ),
        )
        namespace_id = cursor.fetchone()[0]

        repo_ids = {}
        for repo_name, visibility_id, description in [
            (spam_repo, public_visibility_id, SPAM_DESCRIPTION),
            (restore_repo, public_visibility_id, SPAM_DESCRIPTION),
            (ham_repo, public_visibility_id, HAM_DESCRIPTION),
            (private_repo, private_visibility_id, SPAM_DESCRIPTION),
        ]:
            cursor = db.execute_sql(
                f"""
                INSERT INTO "repository" (
                    namespace_user_id, name, visibility_id, description, badge_token
                ) VALUES ({_param(db)}, {_param(db)}, {_param(db)}, {_param(db)}, {_param(db)})
                RETURNING id
                """,
                (namespace_id, repo_name, visibility_id, description, str(uuid4())),
            )
            repo_ids[repo_name] = cursor.fetchone()[0]

    return {
        "namespace": namespace,
        "namespace_id": namespace_id,
        "spam_repo": spam_repo,
        "restore_repo": restore_repo,
        "ham_repo": ham_repo,
        "private_repo": private_repo,
        "repo_ids": repo_ids,
    }


def _cleanup_seeded_namespace(config, seeded):
    with quay_db.write_db(config) as db:
        db.execute_sql(
            f'DELETE FROM "repository" WHERE namespace_user_id = {_param(db)}',
            (seeded["namespace_id"],),
        )
        db.execute_sql(
            f'DELETE FROM "user" WHERE id = {_param(db)}',
            (seeded["namespace_id"],),
        )


def _trained_classifier(config):
    created = store.create_classifier(
        config,
        {"name": "live-quay-db", "enabled": True, "scan_threshold": 0.5},
    )
    store.add_training_example(
        config,
        created["uuid"],
        {"text": SPAM_DESCRIPTION, "label": "spam"},
    )
    store.add_training_example(
        config,
        created["uuid"],
        {"text": HAM_DESCRIPTION, "label": "ham"},
    )
    classifier.train_classifier(config, created["uuid"], artifact_version="live-quay-db-v1")
    store.update_policy(
        config,
        {
            "scan_threshold": 0.5,
            "scan_dry_run": False,
            "include_private": False,
            "quarantine_description": QUARANTINE_DESCRIPTION,
            "max_repos": 10000,
            "batch_size": 200,
        },
    )
    return created


def _repo_description(config, repository_id):
    with quay_db.write_db(config) as db:
        description, exists = quay_db.fetch_repository_description(db, repository_id)
    assert exists
    return description


def _review_record(config, namespace, repository):
    records = store.list_review(
        config,
        statuses=["flagged", "quarantined", "restored", "redacted"],
        limit=1000,
    )
    for record in records:
        if record["namespace_name"] == namespace and record["repository_name"] == repository:
            return record
    raise AssertionError(f"missing review record for {namespace}/{repository}")


def _action_count(config, action):
    with connect_state_db(config) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM spam_action_history WHERE action = ?",
            (action,),
        ).fetchone()
    return row[0]


def test_live_quay_db_scan_quarantine_restore_and_redact(tmp_path):
    config = _config(tmp_path)
    seeded = _seed_namespace_and_repos(config)
    try:
        _trained_classifier(config)

        preview = scanner.preview(config, limit=10000)
        preview_repos = {
            f"{match['namespace_name']}/{match['repository_name']}" for match in preview["matches"]
        }
        assert f"{seeded['namespace']}/{seeded['spam_repo']}" in preview_repos
        assert f"{seeded['namespace']}/{seeded['restore_repo']}" in preview_repos
        assert f"{seeded['namespace']}/{seeded['ham_repo']}" not in preview_repos
        assert f"{seeded['namespace']}/{seeded['private_repo']}" not in preview_repos

        run = scanner.run_scan(config, source="live-e2e", dry_run=False, operator="pytest")
        assert run["status"] == "completed"
        assert run["repos_matched"] >= 2
        assert run["repos_flagged"] >= 2

        restore_record = _review_record(config, seeded["namespace"], seeded["restore_repo"])
        quarantined = remediation.quarantine(config, restore_record["uuid"], operator="pytest")
        assert quarantined["status"] == "quarantined"
        assert (
            _repo_description(config, seeded["repo_ids"][seeded["restore_repo"]])
            == QUARANTINE_DESCRIPTION
        )

        restored = remediation.restore(config, restore_record["uuid"], operator="pytest")
        assert restored["status"] == "restored"
        assert (
            _repo_description(config, seeded["repo_ids"][seeded["restore_repo"]])
            == SPAM_DESCRIPTION
        )

        redact_record = _review_record(config, seeded["namespace"], seeded["spam_repo"])
        remediation.quarantine(config, redact_record["uuid"], operator="pytest")
        redacted = remediation.redact(
            config,
            redact_record["uuid"],
            redacted_description=REDACTED_DESCRIPTION,
            operator="pytest",
        )
        assert redacted["status"] == "redacted"
        assert (
            _repo_description(config, seeded["repo_ids"][seeded["spam_repo"]])
            == REDACTED_DESCRIPTION
        )
        assert _repo_description(config, seeded["repo_ids"][seeded["ham_repo"]]) == HAM_DESCRIPTION
        assert (
            _repo_description(config, seeded["repo_ids"][seeded["private_repo"]])
            == SPAM_DESCRIPTION
        )

        assert _action_count(config, "quarantine") == 2
        assert _action_count(config, "restore") == 1
        assert _action_count(config, "redact") == 1
    finally:
        _cleanup_seeded_namespace(config, seeded)
