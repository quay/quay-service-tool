import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime

from . import DEFAULT_QUARANTINE_DESCRIPTION


DEFAULT_STATE_DB_URI = "sqlite:///spam_detection_state.db"


def utcnow():
    return datetime.utcnow().isoformat(timespec="seconds")


def new_uuid():
    return str(uuid.uuid4())


def state_db_uri(config):
    return config.get("SPAM_DETECTION_STATE_DB_URI") or DEFAULT_STATE_DB_URI


def sqlite_path_from_uri(uri):
    if uri.startswith("sqlite:////"):
        return "/" + uri.removeprefix("sqlite:////")
    if uri.startswith("sqlite:///"):
        return uri.removeprefix("sqlite:///")
    if uri.startswith("sqlite://"):
        return uri.removeprefix("sqlite://")
    return uri


def connect_state_db(config):
    db_path = sqlite_path_from_uri(state_db_uri(config))
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def state_transaction(config):
    conn = connect_state_db(config)
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


JSON_FIELDS = {"hard_filter_results"}


def row_to_dict(row):
    if row is None:
        return None
    result = dict(row)
    for key, value in list(result.items()):
        if (key.endswith("_json") or key in JSON_FIELDS) and value:
            result[key] = json.loads(value)
    return result


def json_dumps(value):
    return json.dumps(value or {}, sort_keys=True)


def migrate_state_db(config):
    with connect_state_db(config) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS spam_classifier (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                training_corpus_version TEXT,
                artifact_version TEXT UNIQUE,
                artifact_sha256 TEXT,
                artifact_path TEXT,
                model_snapshot_json TEXT,
                base_model_snapshot_json TEXT,
                base_artifact_version TEXT,
                base_artifact_sha256 TEXT,
                feature_config_json TEXT NOT NULL DEFAULT '{}',
                scan_threshold REAL NOT NULL DEFAULT 0.9,
                ingress_threshold REAL NOT NULL DEFAULT 0.9,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_by TEXT,
                updated_by TEXT
            );

            CREATE INDEX IF NOT EXISTS spam_classifier_enabled_updated_idx
                ON spam_classifier(enabled, updated_at);

            CREATE TABLE IF NOT EXISTS spam_training_example (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                classifier_id INTEGER NOT NULL,
                repository_id INTEGER,
                namespace_name TEXT,
                repository_name TEXT,
                text TEXT NOT NULL,
                label TEXT NOT NULL CHECK(label IN ('spam', 'ham')),
                source TEXT NOT NULL,
                source_ref TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                invalidated_at TEXT,
                invalidated_by TEXT,
                invalidation_reason TEXT,
                FOREIGN KEY(classifier_id) REFERENCES spam_classifier(id)
            );

            CREATE INDEX IF NOT EXISTS spam_training_classifier_label_created_idx
                ON spam_training_example(classifier_id, label, created_at);
            CREATE INDEX IF NOT EXISTS spam_training_source_created_idx
                ON spam_training_example(source, created_at);
            CREATE INDEX IF NOT EXISTS spam_training_repository_created_idx
                ON spam_training_example(repository_id, created_at);

            CREATE TABLE IF NOT EXISTS spam_policy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                active_classifier_id INTEGER,
                scan_threshold REAL NOT NULL DEFAULT 0.9,
                ingress_threshold REAL NOT NULL DEFAULT 0.9,
                include_private INTEGER NOT NULL DEFAULT 0,
                public_only_default INTEGER NOT NULL DEFAULT 1,
                scan_empty_repositories_only INTEGER NOT NULL DEFAULT 1,
                scan_filters_json TEXT NOT NULL DEFAULT '{}',
                quarantine_description TEXT,
                scan_dry_run INTEGER NOT NULL DEFAULT 1,
                max_repos INTEGER NOT NULL DEFAULT 0,
                batch_size INTEGER NOT NULL DEFAULT 200,
                sleep_between_batches REAL NOT NULL DEFAULT 0.5,
                rescan_terminal_records INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT,
                FOREIGN KEY(active_classifier_id) REFERENCES spam_classifier(id)
            );

            CREATE TABLE IF NOT EXISTS spam_scan_run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                dry_run INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
                started_at TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL,
                completed_at TEXT,
                classifier_snapshot_json TEXT NOT NULL DEFAULT '{}',
                policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
                repos_scanned INTEGER NOT NULL DEFAULT 0,
                repos_matched INTEGER NOT NULL DEFAULT 0,
                repos_flagged INTEGER NOT NULL DEFAULT 0,
                repos_quarantined INTEGER NOT NULL DEFAULT 0,
                repos_skipped_terminal INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_by TEXT
            );

            CREATE INDEX IF NOT EXISTS spam_scan_run_started_idx
                ON spam_scan_run(started_at);
            CREATE UNIQUE INDEX IF NOT EXISTS spam_scan_run_one_running_idx
                ON spam_scan_run(status)
                WHERE status = 'running';

            CREATE TABLE IF NOT EXISTS spam_scan_match (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                run_id INTEGER NOT NULL,
                repository_id INTEGER NOT NULL,
                namespace_name TEXT NOT NULL,
                repository_name TEXT NOT NULL,
                visibility TEXT,
                description_excerpt TEXT,
                classifier_score REAL NOT NULL,
                explanation_json TEXT NOT NULL DEFAULT '{}',
                is_empty INTEGER NOT NULL DEFAULT 0,
                hard_filter_results TEXT NOT NULL DEFAULT '{}',
                quarantine_record_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES spam_scan_run(id),
                FOREIGN KEY(quarantine_record_id) REFERENCES spam_quarantine_record(id)
            );

            CREATE INDEX IF NOT EXISTS spam_scan_match_run_score_idx
                ON spam_scan_match(run_id, classifier_score, id);
            CREATE INDEX IF NOT EXISTS spam_scan_match_repository_created_idx
                ON spam_scan_match(repository_id, created_at);

            CREATE TABLE IF NOT EXISTS spam_quarantine_record (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                repository_id INTEGER NOT NULL,
                namespace_name TEXT NOT NULL,
                repository_name TEXT NOT NULL,
                visibility TEXT,
                status TEXT NOT NULL CHECK(status IN ('flagged', 'quarantined', 'restored', 'dismissed', 'redacted')),
                original_description TEXT,
                quarantine_description TEXT,
                redacted_description TEXT,
                classifier_score REAL NOT NULL,
                classifier_snapshot_json TEXT NOT NULL DEFAULT '{}',
                description_fingerprint TEXT,
                terminal_classifier_snapshot_json TEXT,
                terminal_description_fingerprint TEXT,
                review_source TEXT NOT NULL DEFAULT 'scan',
                run_id INTEGER,
                match_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                actioned_by TEXT,
                actioned_at TEXT,
                FOREIGN KEY(run_id) REFERENCES spam_scan_run(id),
                FOREIGN KEY(match_id) REFERENCES spam_scan_match(id)
            );

            CREATE INDEX IF NOT EXISTS spam_quarantine_status_score_idx
                ON spam_quarantine_record(status, classifier_score, id);
            CREATE INDEX IF NOT EXISTS spam_quarantine_repository_status_idx
                ON spam_quarantine_record(repository_id, status);
            CREATE UNIQUE INDEX IF NOT EXISTS spam_quarantine_one_active_repo_idx
                ON spam_quarantine_record(repository_id)
                WHERE status IN ('flagged', 'quarantined');

            CREATE TABLE IF NOT EXISTS spam_action_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                quarantine_record_id INTEGER,
                action TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT,
                operator TEXT,
                created_at TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(quarantine_record_id) REFERENCES spam_quarantine_record(id)
            );

            CREATE INDEX IF NOT EXISTS spam_action_history_record_created_idx
                ON spam_action_history(quarantine_record_id, created_at);
            CREATE INDEX IF NOT EXISTS spam_action_history_action_created_idx
                ON spam_action_history(action, created_at);
            """
        )
        _ensure_column(
            conn,
            "spam_scan_match",
            "hard_filter_results",
            "TEXT NOT NULL DEFAULT '{}'",
        )
        _ensure_column(
            conn,
            "spam_policy",
            "rescan_terminal_records",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "spam_scan_run",
            "repos_skipped_terminal",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(conn, "spam_scan_run", "heartbeat_at", "TEXT")
        conn.execute(
            "UPDATE spam_scan_run SET heartbeat_at = started_at WHERE heartbeat_at IS NULL"
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS spam_scan_run_status_heartbeat_idx
            ON spam_scan_run(status, heartbeat_at)
            """
        )
        _ensure_column(conn, "spam_quarantine_record", "description_fingerprint", "TEXT")
        _ensure_column(
            conn,
            "spam_quarantine_record",
            "terminal_classifier_snapshot_json",
            "TEXT",
        )
        _ensure_column(
            conn,
            "spam_quarantine_record",
            "terminal_description_fingerprint",
            "TEXT",
        )
        _ensure_column(
            conn,
            "spam_quarantine_record",
            "review_source",
            "TEXT NOT NULL DEFAULT 'scan'",
        )
        _ensure_column(conn, "spam_training_example", "invalidated_at", "TEXT")
        _ensure_column(conn, "spam_training_example", "invalidated_by", "TEXT")
        _ensure_column(conn, "spam_training_example", "invalidation_reason", "TEXT")
        _ensure_column(conn, "spam_classifier", "base_model_snapshot_json", "TEXT")
        _ensure_column(conn, "spam_classifier", "base_artifact_version", "TEXT")
        _ensure_column(conn, "spam_classifier", "base_artifact_sha256", "TEXT")
        conn.execute(
            """
            UPDATE spam_classifier
            SET base_artifact_version = json_extract(base_model_snapshot_json, '$.version')
            WHERE base_model_snapshot_json IS NOT NULL
              AND base_artifact_version IS NULL
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS spam_classifier_base_artifact_version_idx
            ON spam_classifier(base_artifact_version)
            WHERE base_artifact_version IS NOT NULL
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS spam_training_one_review_decision_idx
            ON spam_training_example(source_ref)
            WHERE source = 'review_decision' AND invalidated_at IS NULL
            """
        )
        conn.execute("UPDATE spam_policy SET scan_empty_repositories_only = 1")


def _ensure_column(conn, table, column, definition):
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_policy(conn, config):
    row = conn.execute("SELECT * FROM spam_policy ORDER BY id LIMIT 1").fetchone()
    if row:
        return row

    now = utcnow()
    conn.execute(
        """
        INSERT INTO spam_policy (
            uuid, scan_threshold, ingress_threshold, include_private,
            public_only_default, scan_empty_repositories_only, scan_filters_json,
            quarantine_description, scan_dry_run, max_repos, batch_size,
            sleep_between_batches, rescan_terminal_records, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_uuid(),
            float(config.get("SPAM_DETECTION_SCAN_THRESHOLD", 0.9)),
            float(config.get("SPAM_DETECTION_INGRESS_THRESHOLD", 0.9)),
            1 if config.get("SPAM_DETECTION_INCLUDE_PRIVATE", False) else 0,
            0 if config.get("SPAM_DETECTION_INCLUDE_PRIVATE", False) else 1,
            1,
            "{}",
            config.get(
                "SPAM_DETECTION_QUARANTINE_DESCRIPTION",
                DEFAULT_QUARANTINE_DESCRIPTION,
            ),
            1 if config.get("SPAM_DETECTION_SCAN_DRY_RUN", True) else 0,
            int(config.get("SPAM_DETECTION_MAX_REPOS", 0)),
            int(config.get("SPAM_DETECTION_BATCH_SIZE", 200)),
            float(config.get("SPAM_DETECTION_SLEEP_BETWEEN_BATCHES", 0.5)),
            1 if config.get("SPAM_DETECTION_RESCAN_TERMINAL_RECORDS", False) else 0,
            now,
            now,
        ),
    )
    return conn.execute("SELECT * FROM spam_policy ORDER BY id LIMIT 1").fetchone()
