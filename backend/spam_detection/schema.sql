CREATE TABLE IF NOT EXISTS spam_classifier (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    training_corpus_version TEXT,
    artifact_version TEXT UNIQUE,
    artifact_sha256 TEXT,
    artifact_path TEXT,
    base_artifact_path TEXT,
    base_artifact_version TEXT,
    base_artifact_sha256 TEXT,
    feature_config_json TEXT NOT NULL DEFAULT '{}',
    scan_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.9,
    ingress_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.9,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT,
    updated_by TEXT
);
CREATE INDEX IF NOT EXISTS spam_classifier_enabled_updated_idx
    ON spam_classifier(enabled, updated_at);
CREATE UNIQUE INDEX IF NOT EXISTS spam_classifier_one_enabled_idx
    ON spam_classifier(enabled) WHERE enabled = 1;
CREATE UNIQUE INDEX IF NOT EXISTS spam_classifier_base_artifact_version_idx
    ON spam_classifier(base_artifact_version)
    WHERE base_artifact_version IS NOT NULL;

CREATE TABLE IF NOT EXISTS spam_training_example (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT NOT NULL UNIQUE,
    classifier_id BIGINT NOT NULL REFERENCES spam_classifier(id),
    repository_id BIGINT,
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
    invalidation_reason TEXT
);
CREATE INDEX IF NOT EXISTS spam_training_classifier_label_created_idx
    ON spam_training_example(classifier_id, label, created_at);
CREATE INDEX IF NOT EXISTS spam_training_source_created_idx
    ON spam_training_example(source, created_at);
CREATE INDEX IF NOT EXISTS spam_training_repository_created_idx
    ON spam_training_example(repository_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS spam_training_one_review_decision_idx
    ON spam_training_example(source_ref)
    WHERE source = 'review_decision' AND invalidated_at IS NULL;

CREATE TABLE IF NOT EXISTS spam_policy (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT NOT NULL UNIQUE,
    active_classifier_id BIGINT REFERENCES spam_classifier(id),
    scan_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.9,
    ingress_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.9,
    include_private INTEGER NOT NULL DEFAULT 0,
    public_only_default INTEGER NOT NULL DEFAULT 1,
    scan_empty_repositories_only INTEGER NOT NULL DEFAULT 1,
    scan_filters_json TEXT NOT NULL DEFAULT '{}',
    quarantine_description TEXT,
    scan_dry_run INTEGER NOT NULL DEFAULT 1,
    max_repos INTEGER NOT NULL DEFAULT 0,
    batch_size INTEGER NOT NULL DEFAULT 200,
    sleep_between_batches DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    rescan_terminal_records INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT
);

CREATE TABLE IF NOT EXISTS spam_scan_run (
    id BIGSERIAL PRIMARY KEY,
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
    ON spam_scan_run(status) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS spam_scan_run_status_heartbeat_idx
    ON spam_scan_run(status, heartbeat_at);

CREATE TABLE IF NOT EXISTS spam_quarantine_record (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT NOT NULL UNIQUE,
    repository_id BIGINT NOT NULL,
    namespace_name TEXT NOT NULL,
    repository_name TEXT NOT NULL,
    visibility TEXT,
    status TEXT NOT NULL CHECK(status IN ('flagged', 'quarantined', 'restored', 'dismissed', 'redacted')),
    original_description TEXT,
    quarantine_description TEXT,
    redacted_description TEXT,
    classifier_score DOUBLE PRECISION NOT NULL,
    classifier_snapshot_json TEXT NOT NULL DEFAULT '{}',
    description_fingerprint TEXT,
    terminal_classifier_snapshot_json TEXT,
    terminal_description_fingerprint TEXT,
    review_source TEXT NOT NULL DEFAULT 'scan',
    run_id BIGINT REFERENCES spam_scan_run(id),
    match_id BIGINT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    actioned_by TEXT,
    actioned_at TEXT
);
CREATE INDEX IF NOT EXISTS spam_quarantine_status_score_idx
    ON spam_quarantine_record(status, classifier_score, id);
CREATE INDEX IF NOT EXISTS spam_quarantine_repository_status_idx
    ON spam_quarantine_record(repository_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS spam_quarantine_one_active_repo_idx
    ON spam_quarantine_record(repository_id)
    WHERE status IN ('flagged', 'quarantined');

CREATE TABLE IF NOT EXISTS spam_scan_match (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT NOT NULL UNIQUE,
    run_id BIGINT NOT NULL REFERENCES spam_scan_run(id),
    repository_id BIGINT NOT NULL,
    namespace_name TEXT NOT NULL,
    repository_name TEXT NOT NULL,
    visibility TEXT,
    description_excerpt TEXT,
    classifier_score DOUBLE PRECISION NOT NULL,
    explanation_json TEXT NOT NULL DEFAULT '{}',
    is_empty INTEGER NOT NULL DEFAULT 0,
    hard_filter_results TEXT NOT NULL DEFAULT '{}',
    quarantine_record_id BIGINT REFERENCES spam_quarantine_record(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS spam_scan_match_run_score_idx
    ON spam_scan_match(run_id, classifier_score, id);
CREATE INDEX IF NOT EXISTS spam_scan_match_repository_created_idx
    ON spam_scan_match(repository_id, created_at);

CREATE TABLE IF NOT EXISTS spam_action_history (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT NOT NULL UNIQUE,
    quarantine_record_id BIGINT REFERENCES spam_quarantine_record(id),
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    operator TEXT,
    created_at TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS spam_action_history_record_created_idx
    ON spam_action_history(quarantine_record_id, created_at);
CREATE INDEX IF NOT EXISTS spam_action_history_action_created_idx
    ON spam_action_history(action, created_at);
