import sqlite3

import pytest

from spam_detection import classifier, quay_db, remediation, scanner, store


def _config(tmp_path, quay_db_path):
    return {
        "SPAM_DETECTION_STATE_DB_URI": f"sqlite:///{tmp_path / 'state.db'}",
        "SPAM_DETECTION_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "SPAM_DETECTION_READONLY_DB_URI": f"sqlite:///{quay_db_path}",
        "SPAM_DETECTION_WRITE_DB_URI": f"sqlite:///{quay_db_path}",
        "SPAM_DETECTION_SLEEP_BETWEEN_BATCHES": 0,
        "SPAM_DETECTION_BATCH_SIZE": 10,
    }


def _create_quay_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE "user" (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL
        );
        CREATE TABLE "visibility" (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE "repository" (
            id INTEGER PRIMARY KEY,
            namespace_user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            visibility_id INTEGER NOT NULL,
            description TEXT,
            state INTEGER NOT NULL
        );
        CREATE TABLE "tag" (
            id INTEGER PRIMARY KEY,
            repository_id INTEGER NOT NULL,
            lifetime_end_ms INTEGER,
            hidden INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO "user" (id, username) VALUES (1, 'publicns'), (2, 'privatens');
        INSERT INTO "visibility" (id, name) VALUES (1, 'public'), (2, 'private');
        INSERT INTO "repository"
            (id, namespace_user_id, name, visibility_id, description, state)
        VALUES
            (1, 1, 'spam', 1, 'casino bonus jackpot', 0),
            (2, 2, 'private-spam', 2, 'casino bonus jackpot', 0),
            (3, 1, 'ham', 1, 'container image documentation', 0),
            (4, 1, 'nonempty-spam', 1, 'casino bonus jackpot', 0);
        INSERT INTO "tag" (id, repository_id, lifetime_end_ms, hidden)
        VALUES (1, 4, NULL, 0);
        """
    )
    conn.commit()
    conn.close()


def _trained_classifier(config):
    created = store.create_classifier(
        config,
        {"name": "test", "enabled": True, "scan_threshold": 0.5},
    )
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
    classifier.train_classifier(config, created["uuid"], artifact_version="test-v1")
    store.update_policy(config, {"scan_threshold": 0.5})
    return created


def test_preview_scans_public_repositories_by_default(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)

    result = scanner.preview(config, limit=10)

    repositories = {
        f"{match['namespace_name']}/{match['repository_name']}" for match in result["matches"]
    }
    assert "publicns/spam" in repositories
    assert "privatens/private-spam" not in repositories
    assert "publicns/nonempty-spam" not in repositories
    assert all(match["hard_filter_results"]["repository_empty"]["matched"] for match in result["matches"])


def test_non_empty_repositories_are_hard_excluded_from_scan_and_review(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(
        config,
        {
            "scan_dry_run": False,
            "scan_empty_repositories_only": False,
        },
    )

    preview = scanner.preview(config, policy_override={"scan_empty_repositories_only": False}, limit=10)
    preview_repositories = {
        f"{match['namespace_name']}/{match['repository_name']}" for match in preview["matches"]
    }
    assert "publicns/spam" in preview_repositories
    assert "publicns/nonempty-spam" not in preview_repositories
    assert preview["policy"]["scan_empty_repositories_only"] is True

    run = scanner.run_scan(config, dry_run=False)
    matches = store.list_matches(config, run["uuid"])
    matched_repositories = {
        f"{match['namespace_name']}/{match['repository_name']}" for match in matches
    }
    review_repositories = {
        f"{record['namespace_name']}/{record['repository_name']}" for record in store.list_review(config)
    }

    assert "publicns/spam" in matched_repositories
    assert "publicns/nonempty-spam" not in matched_repositories
    assert "publicns/nonempty-spam" not in review_repositories
    assert run["policy_snapshot_json"]["scan_empty_repositories_only"] is True
    assert all(match["is_empty"] for match in matches)
    assert all(match["hard_filter_results"]["repository_empty"]["required"] for match in matches)
    assert all(match["hard_filter_results"]["repository_empty"]["matched"] for match in matches)


def test_readonly_quay_connection_rejects_repository_updates(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)

    with quay_db.readonly_db(config) as db:
        with pytest.raises(Exception):
            quay_db.update_repository_description(db, 1, "changed")

    conn = sqlite3.connect(quay_db_path)
    description = conn.execute('SELECT description FROM "repository" WHERE id = 1').fetchone()[0]
    conn.close()
    assert description == "casino bonus jackpot"


def test_quarantine_writes_repository_description_directly(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False, "quarantine_description": "quarantined"})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    updated = remediation.quarantine(config, record["uuid"], operator="tester")

    conn = sqlite3.connect(quay_db_path)
    description = conn.execute('SELECT description FROM "repository" WHERE id = 1').fetchone()[0]
    conn.close()

    assert updated["status"] == "quarantined"
    assert description == "quarantined"


def test_default_quarantine_description_includes_restore_instructions(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.quarantine(config, record["uuid"], operator="tester")

    conn = sqlite3.connect(quay_db_path)
    description = conn.execute('SELECT description FROM "repository" WHERE id = 1').fetchone()[0]
    conn.close()

    assert "contact Quay support" in description
    assert "remove promotional, deceptive, or unrelated link content" in description
    assert "published support timeline" in description


def test_scan_stores_compact_classifier_snapshots(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False})

    run = scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]

    assert "token_spam_counts" not in run["classifier_snapshot_json"]
    assert "token_ham_counts" not in run["classifier_snapshot_json"]
    assert "token_spam_counts" not in record["classifier_snapshot_json"]
    assert "token_ham_counts" not in record["classifier_snapshot_json"]


def test_scan_rejects_when_another_scan_is_running(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.create_scan_run(config, "test", True, {}, {}, operator="tester")

    with pytest.raises(ValueError):
        scanner.run_scan(config, dry_run=True)


def test_quarantine_preserves_latest_description_for_restore(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False, "quarantine_description": "quarantined"})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    conn = sqlite3.connect(quay_db_path)
    conn.execute('UPDATE "repository" SET description = ? WHERE id = 1', ("legitimate update",))
    conn.commit()
    conn.close()

    quarantined = remediation.quarantine(config, record["uuid"], operator="tester")
    restored = remediation.restore(config, record["uuid"], operator="tester")

    conn = sqlite3.connect(quay_db_path)
    description = conn.execute('SELECT description FROM "repository" WHERE id = 1').fetchone()[0]
    conn.close()

    assert quarantined["original_description"] == "legitimate update"
    assert restored["status"] == "restored"
    assert description == "legitimate update"


def test_restore_rejects_when_quarantined_description_changed(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False, "quarantine_description": "quarantined"})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.quarantine(config, record["uuid"], operator="tester")
    conn = sqlite3.connect(quay_db_path)
    conn.execute('UPDATE "repository" SET description = ? WHERE id = 1', ("manual moderation edit",))
    conn.commit()
    conn.close()

    with pytest.raises(remediation.RemediationError):
        remediation.restore(config, record["uuid"], operator="tester")


def test_redact_requires_explicit_description(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False, "quarantine_description": "quarantined"})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.quarantine(config, record["uuid"], operator="tester")

    with pytest.raises(remediation.RemediationError):
        remediation.redact(config, record["uuid"], operator="tester")

    redacted = remediation.redact(
        config,
        record["uuid"],
        redacted_description="[redacted]",
        operator="tester",
    )

    conn = sqlite3.connect(quay_db_path)
    description = conn.execute('SELECT description FROM "repository" WHERE id = 1').fetchone()[0]
    conn.close()

    assert redacted["status"] == "redacted"
    assert description == "[redacted]"
