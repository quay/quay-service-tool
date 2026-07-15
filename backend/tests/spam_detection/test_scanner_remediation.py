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
        "SPAM_DETECTION_MIN_SPAM_EXAMPLES": 1,
        "SPAM_DETECTION_MIN_HAM_EXAMPLES": 1,
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
            (1, 1, 'spam', 1, 'casino bonus jackpot https://spam.example', 0),
            (2, 2, 'private-spam', 2, 'casino bonus jackpot https://spam.example', 0),
            (3, 1, 'ham', 1, 'container image documentation', 0),
            (4, 1, 'nonempty-spam', 1, 'casino bonus jackpot https://spam.example', 0);
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


def test_description_without_hyperlink_is_hard_excluded(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    conn = sqlite3.connect(quay_db_path)
    conn.execute(
        'UPDATE "repository" SET description = ? WHERE id = 1',
        ("casino bonus jackpot",),
    )
    conn.commit()
    conn.close()
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)

    preview = scanner.preview(config, limit=10)
    run = scanner.run_scan(config, dry_run=False)

    assert preview["repos_matched"] == 0
    assert run["repos_matched"] == 0
    assert store.list_review(config) == []


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
    assert description == "casino bonus jackpot https://spam.example"


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


def test_dismiss_records_ham_feedback_for_next_training(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    created = _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    dismissed = remediation.dismiss(config, record["uuid"], operator="reviewer")

    examples = store.list_training_examples(config, created["id"])
    feedback = [example for example in examples if example["source"] == "review_decision"]
    assert len(feedback) == 1
    assert feedback[0]["label"] == "ham"
    assert feedback[0]["text"] == "casino bonus jackpot https://spam.example"
    assert feedback[0]["repository_id"] == 1
    assert feedback[0]["source_ref"] == record["uuid"]
    audit = store.list_audit_actions(config)
    dismiss_action = next(action for action in audit if action["action"] == "dismiss")
    assert dismiss_action["record_uuid"] == record["uuid"]
    assert dismiss_action["namespace_name"] == "publicns"
    assert dismiss_action["repository_name"] == "spam"
    assert dismissed["description_fingerprint"] == store.description_fingerprint(
        "casino bonus jackpot https://spam.example"
    )
    assert dismissed["terminal_description_fingerprint"] == store.description_fingerprint(
        "casino bonus jackpot https://spam.example"
    )
    assert dismissed["terminal_classifier_snapshot_json"]["artifact_version"] == "test-v1"

    trained = classifier.train_classifier(config, created["uuid"], artifact_version="test-v2")
    assert trained["model_snapshot_json"]["training_metrics"]["example_count"] == 3
    assert trained["model_snapshot_json"]["training_metrics"]["ham_examples"] == 2


def test_restore_records_ham_feedback_after_quarantine_spam_feedback(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    created = _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False, "quarantine_description": "quarantined"})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.quarantine(config, record["uuid"], operator="reviewer")
    restored = remediation.restore(config, record["uuid"], operator="reviewer")

    feedback = [
        (example["label"], example["text"], example["source_ref"])
        for example in store.list_training_examples(config, created["id"])
        if example["source"] == "review_decision"
    ]
    assert [(label, text) for label, text, _ in feedback] == [
        ("ham", "casino bonus jackpot https://spam.example"),
    ]
    assert all(source_ref for _, _, source_ref in feedback)
    assert store.list_review(config, statuses=["restored"])[0]["review_label"] == "ham"
    assert restored["terminal_description_fingerprint"] == store.description_fingerprint(
        "casino bonus jackpot https://spam.example"
    )


def test_reopen_restored_record_invalidates_ham_feedback_and_allows_requarantine(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    created = _trained_classifier(config)
    store.update_policy(
        config,
        {"scan_dry_run": False, "quarantine_description": "quarantined"},
    )

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.quarantine(config, record["uuid"], operator="reviewer")
    remediation.restore(config, record["uuid"], operator="reviewer")

    reopened = remediation.reopen(
        config,
        record["uuid"],
        reason="Restore was approved in error",
        operator="lead-reviewer",
    )

    assert reopened["status"] == "flagged"
    assert reopened["terminal_classifier_snapshot_json"] is None
    assert reopened["terminal_description_fingerprint"] is None
    assert store.list_review(config)[0]["uuid"] == record["uuid"]
    feedback = [
        example
        for example in store.list_training_examples(config, created["id"])
        if example["source"] == "review_decision"
    ]
    assert feedback == []

    state_conn = sqlite3.connect(tmp_path / "state.db")
    invalidated = state_conn.execute(
        """
        SELECT invalidated_by, invalidation_reason
        FROM spam_training_example
        WHERE source = 'review_decision' AND label = 'ham'
        """
    ).fetchone()
    state_conn.close()
    assert invalidated == ("lead-reviewer", "Restore was approved in error")

    reopen_action = next(
        action for action in store.list_audit_actions(config) if action["action"] == "reopen"
    )
    assert reopen_action["from_status"] == "restored"
    assert reopen_action["to_status"] == "flagged"
    assert reopen_action["operator"] == "lead-reviewer"
    assert reopen_action["details_json"] == {
        "invalidated_training_examples": 1,
        "reason": "Restore was approved in error",
    }

    requarantined = remediation.quarantine(
        config, record["uuid"], operator="lead-reviewer"
    )
    assert requarantined["status"] == "quarantined"
    conn = sqlite3.connect(quay_db_path)
    description = conn.execute(
        'SELECT description FROM "repository" WHERE id = 1'
    ).fetchone()[0]
    conn.close()
    assert description == "quarantined"
    trained = classifier.train_classifier(
        config, created["uuid"], artifact_version="test-v2"
    )
    metrics = trained["model_snapshot_json"]["training_metrics"]
    assert metrics["example_count"] == 3
    assert metrics["spam_examples"] == 2
    assert metrics["ham_examples"] == 1


def test_reopen_dismissed_record_invalidates_ham_feedback(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    created = _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.dismiss(config, record["uuid"], operator="reviewer")
    reopened = remediation.reopen(
        config,
        record["uuid"],
        reason="Dismissal was approved in error",
        operator="lead-reviewer",
    )

    assert reopened["status"] == "flagged"
    feedback = [
        example
        for example in store.list_training_examples(config, created["id"])
        if example["source"] == "review_decision"
    ]
    assert feedback == []
    reopen_action = next(
        action for action in store.list_audit_actions(config) if action["action"] == "reopen"
    )
    assert reopen_action["from_status"] == "dismissed"
    assert reopen_action["details_json"] == {
        "invalidated_training_examples": 1,
        "reason": "Dismissal was approved in error",
    }


def test_review_match_can_be_reclassified_for_training(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    created = _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    first = remediation.classify(config, record["uuid"], "ham", operator="reviewer")
    assert store.list_review(config)[0]["review_label"] == "ham"
    second = remediation.classify(config, record["uuid"], "spam", operator="reviewer")

    assert first["status"] == "flagged"
    assert second["status"] == "flagged"
    feedback = [
        example
        for example in store.list_training_examples(config, created["id"])
        if example["source"] == "review_decision"
    ]
    assert [(example["label"], example["source_ref"]) for example in feedback] == [
        ("spam", record["uuid"])
    ]
    classify_actions = [
        action for action in store.list_audit_actions(config) if action["action"] == "classify"
    ]
    assert classify_actions[0]["details_json"] == {
        "invalidated_training_examples": 1,
        "label": "spam",
    }


def test_explicit_label_is_rejected_after_remediation_decision(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(
        config,
        {"scan_dry_run": False, "quarantine_description": "quarantined"},
    )

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.quarantine(config, record["uuid"], operator="reviewer")

    with pytest.raises(
        remediation.RemediationError,
        match="explicit labels are only allowed for flagged records",
    ):
        remediation.classify(config, record["uuid"], "ham", operator="reviewer")

    reviewed = store.list_review(config)[0]
    assert reviewed["status"] == "quarantined"
    assert reviewed["review_label"] == "spam"


def test_reopen_requires_reason_and_empty_repository(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(
        config,
        {"scan_dry_run": False, "quarantine_description": "quarantined"},
    )

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.quarantine(config, record["uuid"], operator="reviewer")
    remediation.restore(config, record["uuid"], operator="reviewer")

    with pytest.raises(remediation.RemediationError, match="reason is required"):
        remediation.reopen(config, record["uuid"], reason=" ", operator="reviewer")

    conn = sqlite3.connect(quay_db_path)
    conn.execute(
        'INSERT INTO "tag" (id, repository_id, lifetime_end_ms, hidden) VALUES (?, ?, ?, ?)',
        (2, 1, None, 0),
    )
    conn.commit()
    conn.close()

    with pytest.raises(remediation.RemediationError, match="only empty repositories"):
        remediation.reopen(
            config,
            record["uuid"],
            reason="Restore was approved in error",
            operator="reviewer",
        )


def test_quarantine_rechecks_empty_repository_after_reopen(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(
        config,
        {"scan_dry_run": False, "quarantine_description": "quarantined"},
    )

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.quarantine(config, record["uuid"], operator="reviewer")
    remediation.restore(config, record["uuid"], operator="reviewer")
    remediation.reopen(
        config,
        record["uuid"],
        reason="Restore was approved in error",
        operator="reviewer",
    )
    conn = sqlite3.connect(quay_db_path)
    conn.execute(
        'INSERT INTO "tag" (id, repository_id, lifetime_end_ms, hidden) VALUES (?, ?, ?, ?)',
        (2, 1, None, 0),
    )
    conn.commit()
    conn.close()

    with pytest.raises(remediation.RemediationError, match="only empty repositories"):
        remediation.quarantine(config, record["uuid"], operator="reviewer")


def test_unchanged_terminal_record_is_not_reopened(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.dismiss(config, record["uuid"], operator="reviewer")

    run = scanner.run_scan(config, dry_run=False)

    assert run["repos_matched"] == 1
    assert run["repos_flagged"] == 0
    assert run["repos_skipped_terminal"] == 1
    assert store.list_review(config) == []


def test_changed_description_reopens_terminal_record(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.dismiss(config, record["uuid"], operator="reviewer")
    conn = sqlite3.connect(quay_db_path)
    conn.execute(
        'UPDATE "repository" SET description = ? WHERE id = 1',
        ("casino bonus jackpot offer https://spam.example",),
    )
    conn.commit()
    conn.close()

    run = scanner.run_scan(config, dry_run=False)

    assert run["repos_flagged"] == 1
    assert run["repos_skipped_terminal"] == 0
    assert store.list_review(config)[0]["description_fingerprint"] == store.description_fingerprint(
        "casino bonus jackpot offer https://spam.example"
    )


def test_new_classifier_artifact_reopens_terminal_record(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    created = _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.dismiss(config, record["uuid"], operator="reviewer")
    classifier.export_artifact(config, created["uuid"], artifact_version="test-v2")

    run = scanner.run_scan(config, dry_run=False)

    assert run["repos_flagged"] == 1
    assert run["repos_skipped_terminal"] == 0


def test_terminal_record_captures_classifier_active_at_review_time(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    created = _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    classifier.export_artifact(config, created["uuid"], artifact_version="test-v2")
    dismissed = remediation.dismiss(config, record["uuid"], operator="reviewer")

    run = scanner.run_scan(config, dry_run=False)

    assert dismissed["terminal_classifier_snapshot_json"]["artifact_version"] == "test-v2"
    assert run["repos_flagged"] == 0
    assert run["repos_skipped_terminal"] == 1


def test_terminal_rescan_policy_reopens_unchanged_record(tmp_path):
    quay_db_path = tmp_path / "quay.db"
    _create_quay_db(quay_db_path)
    config = _config(tmp_path, quay_db_path)
    _trained_classifier(config)
    store.update_policy(config, {"scan_dry_run": False})

    scanner.run_scan(config, dry_run=False)
    record = store.list_review(config)[0]
    remediation.dismiss(config, record["uuid"], operator="reviewer")
    policy = store.update_policy(config, {"rescan_terminal_records": True})

    run = scanner.run_scan(config, dry_run=False)

    assert policy["rescan_terminal_records"] == 1
    assert run["repos_flagged"] == 1
    assert run["repos_skipped_terminal"] == 0
