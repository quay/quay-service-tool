import hashlib
import sqlite3

from .database import (
    connect_state_db,
    ensure_policy,
    json_dumps,
    migrate_state_db,
    new_uuid,
    row_to_dict,
    utcnow,
)


DEFAULT_TOKEN_PATTERN = r"[a-z0-9][a-z0-9_-]*"
MAX_TRAINING_TEXT_LENGTH = 10000


def _validate_probability(value, field):
    value = float(value)
    if value < 0 or value > 1:
        raise ValueError(f"{field} must be between 0 and 1")
    return value


def _validate_nonnegative_int(value, field):
    value = int(value)
    if value < 0:
        raise ValueError(f"{field} must be greater than or equal to 0")
    return value


def _validate_positive_int(value, field):
    value = int(value)
    if value <= 0:
        raise ValueError(f"{field} must be greater than 0")
    return value


def _validate_nonnegative_float(value, field):
    value = float(value)
    if value < 0:
        raise ValueError(f"{field} must be greater than or equal to 0")
    return value


def _validate_feature_config(feature_config):
    feature_config = feature_config or {
        "token_pattern": DEFAULT_TOKEN_PATTERN,
        "include_repository_name": False,
    }
    token_pattern = feature_config.get("token_pattern", DEFAULT_TOKEN_PATTERN)
    if token_pattern != DEFAULT_TOKEN_PATTERN:
        raise ValueError("custom token_pattern is not supported in the initial spam detector")
    return {
        "token_pattern": DEFAULT_TOKEN_PATTERN,
        "include_repository_name": bool(feature_config.get("include_repository_name", False)),
    }


def _validate_training_text(config, text):
    text = text.strip()
    max_length = int(config.get("SPAM_DETECTION_MAX_TRAINING_TEXT_LENGTH", MAX_TRAINING_TEXT_LENGTH))
    if not text:
        raise ValueError("text is required")
    if len(text) > max_length:
        raise ValueError(f"text must be {max_length} characters or fewer")
    return text


def description_fingerprint(description):
    return hashlib.sha256((description or "").encode("utf-8")).hexdigest()


def initialize(config):
    migrate_state_db(config)


def create_classifier(config, payload, operator=None):
    initialize(config)
    now = utcnow()
    feature_config = _validate_feature_config(payload.get("feature_config"))
    scan_threshold = _validate_probability(payload.get("scan_threshold", 0.9), "scan_threshold")
    ingress_threshold = _validate_probability(payload.get("ingress_threshold", 0.9), "ingress_threshold")
    with connect_state_db(config) as conn:
        if payload.get("enabled"):
            conn.execute("UPDATE spam_classifier SET enabled = 0")
        cur = conn.execute(
            """
            INSERT INTO spam_classifier (
                uuid, name, enabled, training_corpus_version, feature_config_json,
                scan_threshold, ingress_threshold, created_at, updated_at,
                created_by, updated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_uuid(),
                payload["name"],
                1 if payload.get("enabled") else 0,
                payload.get("training_corpus_version"),
                json_dumps(feature_config),
                scan_threshold,
                ingress_threshold,
                now,
                now,
                operator,
                operator,
            ),
        )
        classifier_id = cur.lastrowid
        if payload.get("enabled"):
            policy = ensure_policy(conn, config)
            conn.execute(
                """
                UPDATE spam_policy
                SET active_classifier_id = ?, updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (classifier_id, now, operator, policy["id"]),
            )
        return row_to_dict(
            conn.execute("SELECT * FROM spam_classifier WHERE id = ?", (classifier_id,)).fetchone()
        )


def get_classifier_by_id(config, classifier_id):
    with connect_state_db(config) as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM spam_classifier WHERE id = ?", (classifier_id,)).fetchone()
        )


def get_classifier(config, classifier_uuid):
    initialize(config)
    with connect_state_db(config) as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM spam_classifier WHERE uuid = ?", (classifier_uuid,)).fetchone()
        )


def get_classifier_by_db_id(conn, classifier_id):
    return row_to_dict(
        conn.execute("SELECT * FROM spam_classifier WHERE id = ?", (classifier_id,)).fetchone()
    )


def list_classifiers(config):
    initialize(config)
    with connect_state_db(config) as conn:
        return [
            row_to_dict(row)
            for row in conn.execute("SELECT * FROM spam_classifier ORDER BY updated_at DESC, id DESC")
        ]


def update_classifier(config, classifier_uuid, payload, operator=None):
    initialize(config)
    existing = get_classifier(config, classifier_uuid)
    if not existing:
        return None
    now = utcnow()
    fields = []
    params = []
    for key in [
        "name",
        "training_corpus_version",
    ]:
        if key in payload:
            fields.append(f"{key} = ?")
            params.append(payload[key])
    for key in ["scan_threshold", "ingress_threshold"]:
        if key in payload:
            fields.append(f"{key} = ?")
            params.append(_validate_probability(payload[key], key))
    if "enabled" in payload:
        fields.append("enabled = ?")
        params.append(1 if payload["enabled"] else 0)
    if "feature_config" in payload:
        fields.append("feature_config_json = ?")
        params.append(json_dumps(_validate_feature_config(payload["feature_config"])))
    fields.extend(["updated_at = ?", "updated_by = ?"])
    params.extend([now, operator, existing["id"]])

    with connect_state_db(config) as conn:
        if payload.get("enabled"):
            conn.execute("UPDATE spam_classifier SET enabled = 0")
        conn.execute(
            f"UPDATE spam_classifier SET {', '.join(fields)} WHERE id = ?",
            tuple(params),
        )
        if payload.get("enabled"):
            policy = ensure_policy(conn, config)
            conn.execute(
                """
                UPDATE spam_policy
                SET active_classifier_id = ?, updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (existing["id"], now, operator, policy["id"]),
            )
    return get_classifier(config, classifier_uuid)


def add_training_example(config, classifier_uuid, payload, operator=None):
    initialize(config)
    classifier = get_classifier(config, classifier_uuid)
    if not classifier:
        return None
    label = payload["label"].strip().lower()
    if label not in ("spam", "ham"):
        raise ValueError("label must be spam or ham")
    text = _validate_training_text(config, payload["text"])
    now = utcnow()
    with connect_state_db(config) as conn:
        cur = conn.execute(
            """
            INSERT INTO spam_training_example (
                uuid, classifier_id, repository_id, namespace_name, repository_name,
                text, label, source, source_ref, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_uuid(),
                classifier["id"],
                payload.get("repository_id"),
                payload.get("namespace_name"),
                payload.get("repository_name"),
                text,
                label,
                payload.get("source", "manual_review"),
                payload.get("source_ref"),
                operator,
                now,
            ),
        )
        return row_to_dict(
            conn.execute("SELECT * FROM spam_training_example WHERE id = ?", (cur.lastrowid,)).fetchone()
        )


def list_training_examples(config, classifier_id):
    with connect_state_db(config) as conn:
        return [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT * FROM spam_training_example
                WHERE classifier_id = ?
                ORDER BY created_at, id
                """,
                (classifier_id,),
            )
        ]


def update_classifier_artifact(config, classifier_id, artifact, artifact_path, artifact_sha256):
    now = utcnow()
    with connect_state_db(config) as conn:
        conn.execute(
            """
            UPDATE spam_classifier
            SET training_corpus_version = ?, artifact_version = ?,
                artifact_sha256 = ?, artifact_path = ?, model_snapshot_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                artifact.get("training_corpus_version"),
                artifact.get("version"),
                artifact_sha256,
                artifact_path,
                json_dumps(artifact),
                now,
                classifier_id,
            ),
        )
        return get_classifier_by_db_id(conn, classifier_id)


def artifact_version_exists(config, artifact_version, classifier_id=None):
    initialize(config)
    with connect_state_db(config) as conn:
        params = [artifact_version]
        sql = "SELECT id FROM spam_classifier WHERE artifact_version = ?"
        if classifier_id is not None:
            sql += " AND id != ?"
            params.append(classifier_id)
        return conn.execute(sql, tuple(params)).fetchone() is not None


def classifier_snapshot(classifier):
    if not classifier:
        return {}
    return {
        "id": classifier.get("id"),
        "uuid": classifier.get("uuid"),
        "name": classifier.get("name"),
        "artifact_version": classifier.get("artifact_version"),
        "artifact_sha256": classifier.get("artifact_sha256"),
        "training_corpus_version": classifier.get("training_corpus_version"),
        "scan_threshold": classifier.get("scan_threshold"),
        "ingress_threshold": classifier.get("ingress_threshold"),
        "feature_config": classifier.get("feature_config_json"),
    }


def active_classifier_snapshot(config):
    policy = get_policy(config)
    classifier_id = policy.get("active_classifier_id")
    if not classifier_id:
        return {}
    return classifier_snapshot(get_classifier_by_id(config, classifier_id))


def get_policy(config):
    initialize(config)
    with connect_state_db(config) as conn:
        return row_to_dict(ensure_policy(conn, config))


def update_policy(config, payload, operator=None):
    initialize(config)
    now = utcnow()
    allowed = {
        "scan_threshold",
        "ingress_threshold",
        "include_private",
        "public_only_default",
        "quarantine_description",
        "scan_dry_run",
        "max_repos",
        "batch_size",
        "sleep_between_batches",
        "rescan_terminal_records",
    }
    with connect_state_db(config) as conn:
        policy = ensure_policy(conn, config)
        fields = []
        params = []
        if "active_classifier_uuid" in payload:
            classifier = conn.execute(
                "SELECT * FROM spam_classifier WHERE uuid = ?", (payload["active_classifier_uuid"],)
            ).fetchone()
            if not classifier:
                raise ValueError("active_classifier_uuid was not found")
            fields.append("active_classifier_id = ?")
            params.append(classifier["id"])
        for key in allowed:
            if key not in payload:
                continue
            value = payload[key]
            if key in (
                "include_private",
                "public_only_default",
                "scan_dry_run",
                "rescan_terminal_records",
            ):
                value = 1 if value else 0
            elif key in ("scan_threshold", "ingress_threshold"):
                value = _validate_probability(value, key)
            elif key == "batch_size":
                value = _validate_positive_int(value, key)
            elif key == "max_repos":
                value = _validate_nonnegative_int(value, key)
            elif key == "sleep_between_batches":
                value = _validate_nonnegative_float(value, key)
            fields.append(f"{key} = ?")
            params.append(value)
        if "scan_filters" in payload:
            fields.append("scan_filters_json = ?")
            params.append(json_dumps(payload["scan_filters"]))
        if not fields:
            return row_to_dict(policy)
        fields.extend(["updated_at = ?", "updated_by = ?"])
        params.extend([now, operator, policy["id"]])
        conn.execute(f"UPDATE spam_policy SET {', '.join(fields)} WHERE id = ?", tuple(params))
        return row_to_dict(conn.execute("SELECT * FROM spam_policy WHERE id = ?", (policy["id"],)).fetchone())


def create_scan_run(config, source, dry_run, classifier_snapshot, policy_snapshot, operator=None):
    initialize(config)
    now = utcnow()
    with connect_state_db(config) as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO spam_scan_run (
                    uuid, source, dry_run, status, started_at, classifier_snapshot_json,
                    policy_snapshot_json, created_by
                ) VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
                """,
                (
                    new_uuid(),
                    source,
                    1 if dry_run else 0,
                    now,
                    json_dumps(classifier_snapshot),
                    json_dumps(policy_snapshot),
                    operator,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("a spam detection scan is already running") from exc
        return row_to_dict(conn.execute("SELECT * FROM spam_scan_run WHERE id = ?", (cur.lastrowid,)).fetchone())


def update_scan_run(config, run_id, **fields):
    assignments = []
    params = []
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        params.append(value)
    if not assignments:
        return
    params.append(run_id)
    with connect_state_db(config) as conn:
        conn.execute(f"UPDATE spam_scan_run SET {', '.join(assignments)} WHERE id = ?", tuple(params))


def add_scan_match(config, run_id, repository, score, explanation, hard_filter_results=None):
    now = utcnow()
    excerpt = (repository.get("description") or "")[:500]
    with connect_state_db(config) as conn:
        cur = conn.execute(
            """
            INSERT INTO spam_scan_match (
                uuid, run_id, repository_id, namespace_name, repository_name,
                visibility, description_excerpt, classifier_score, explanation_json,
                is_empty, hard_filter_results, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_uuid(),
                run_id,
                repository["id"],
                repository["namespace_name"],
                repository["repository_name"],
                repository.get("visibility"),
                excerpt,
                score,
                json_dumps(explanation),
                1 if repository.get("is_empty") else 0,
                json_dumps(hard_filter_results),
                now,
            ),
        )
        return row_to_dict(conn.execute("SELECT * FROM spam_scan_match WHERE id = ?", (cur.lastrowid,)).fetchone())


def create_flagged_record(
    config,
    match,
    repository,
    classifier_snapshot,
    rescan_terminal_records=False,
):
    now = utcnow()
    fingerprint = description_fingerprint(repository.get("description"))
    with connect_state_db(config) as conn:
        existing = conn.execute(
            """
            SELECT * FROM spam_quarantine_record
            WHERE repository_id = ? AND status IN ('flagged', 'quarantined')
            """,
            (repository["id"],),
        ).fetchone()
        if existing:
            return row_to_dict(existing)
        if not rescan_terminal_records:
            terminal = conn.execute(
                """
                SELECT * FROM spam_quarantine_record
                WHERE repository_id = ?
                  AND status IN ('dismissed', 'restored', 'redacted')
                ORDER BY id DESC
                LIMIT 1
                """,
                (repository["id"],),
            ).fetchone()
            if terminal and _terminal_record_matches(
                terminal,
                fingerprint,
                classifier_snapshot,
            ):
                return None
        try:
            cur = conn.execute(
                """
                INSERT INTO spam_quarantine_record (
                    uuid, repository_id, namespace_name, repository_name, visibility,
                    status, original_description, classifier_score,
                    classifier_snapshot_json, description_fingerprint,
                    run_id, match_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'flagged', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_uuid(),
                    repository["id"],
                    repository["namespace_name"],
                    repository["repository_name"],
                    repository.get("visibility"),
                    repository.get("description"),
                    match["classifier_score"],
                    json_dumps(classifier_snapshot),
                    fingerprint,
                    match["run_id"],
                    match["id"],
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            existing = conn.execute(
                """
                SELECT * FROM spam_quarantine_record
                WHERE repository_id = ? AND status IN ('flagged', 'quarantined')
                """,
                (repository["id"],),
            ).fetchone()
            if existing:
                return row_to_dict(existing)
            raise
        record_id = cur.lastrowid
        conn.execute(
            "UPDATE spam_scan_match SET quarantine_record_id = ? WHERE id = ?",
            (record_id, match["id"]),
        )
        add_action_with_conn(conn, record_id, "flag", None, "flagged", None, {"match_uuid": match["uuid"]})
        return row_to_dict(
            conn.execute("SELECT * FROM spam_quarantine_record WHERE id = ?", (record_id,)).fetchone()
        )


def _terminal_record_matches(record, fingerprint, classifier_snapshot):
    if record["terminal_description_fingerprint"] != fingerprint:
        return False
    terminal_snapshot = row_to_dict(record).get("terminal_classifier_snapshot_json") or {}
    identity_fields = ("artifact_version", "artifact_sha256")
    if not any(classifier_snapshot.get(field) for field in identity_fields):
        return False
    return all(
        terminal_snapshot.get(field) == classifier_snapshot.get(field)
        for field in identity_fields
    )


def add_action_with_conn(conn, record_id, action, from_status, to_status, operator, details):
    action_uuid = new_uuid()
    conn.execute(
        """
        INSERT INTO spam_action_history (
            uuid, quarantine_record_id, action, from_status, to_status,
            operator, created_at, details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (action_uuid, record_id, action, from_status, to_status, operator, utcnow(), json_dumps(details)),
    )
    return action_uuid


def add_action(config, record_id, action, from_status, to_status, operator=None, details=None):
    initialize(config)
    with connect_state_db(config) as conn:
        add_action_with_conn(conn, record_id, action, from_status, to_status, operator, details or {})


def get_quarantine_record(config, record_uuid):
    initialize(config)
    with connect_state_db(config) as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM spam_quarantine_record WHERE uuid = ?", (record_uuid,)).fetchone()
        )


def update_quarantine_record(
    config,
    record_id,
    fields,
    action,
    operator=None,
    details=None,
    training_feedback=None,
):
    now = utcnow()
    if training_feedback:
        training_feedback = dict(training_feedback)
        training_feedback["text"] = _validate_training_text(config, training_feedback["text"])
        training_feedback["label"] = training_feedback["label"].strip().lower()
        if training_feedback["label"] not in ("spam", "ham"):
            raise ValueError("label must be spam or ham")
    with connect_state_db(config) as conn:
        current = conn.execute("SELECT * FROM spam_quarantine_record WHERE id = ?", (record_id,)).fetchone()
        if not current:
            return None
        assignments = []
        params = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            if key.endswith("_json") and not isinstance(value, str):
                value = json_dumps(value)
            params.append(value)
        assignments.extend(["updated_at = ?", "actioned_by = ?", "actioned_at = ?"])
        params.extend([now, operator, now, record_id])
        conn.execute(f"UPDATE spam_quarantine_record SET {', '.join(assignments)} WHERE id = ?", tuple(params))
        updated = conn.execute("SELECT * FROM spam_quarantine_record WHERE id = ?", (record_id,)).fetchone()
        action_uuid = add_action_with_conn(
            conn,
            record_id,
            action,
            current["status"],
            updated["status"],
            operator,
            details or {},
        )
        if training_feedback:
            snapshot = row_to_dict(current).get("classifier_snapshot_json") or {}
            classifier_id = snapshot.get("id")
            classifier = conn.execute(
                "SELECT id FROM spam_classifier WHERE id = ?",
                (classifier_id,),
            ).fetchone()
            if classifier:
                conn.execute(
                    """
                    INSERT INTO spam_training_example (
                        uuid, classifier_id, repository_id, namespace_name,
                        repository_name, text, label, source, source_ref,
                        created_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'review_action', ?, ?, ?)
                    """,
                    (
                        new_uuid(),
                        classifier["id"],
                        current["repository_id"],
                        current["namespace_name"],
                        current["repository_name"],
                        training_feedback["text"],
                        training_feedback["label"],
                        action_uuid,
                        operator,
                        now,
                    ),
                )
        return row_to_dict(updated)


def update_quarantine_fields(config, record_id, fields):
    assignments = []
    params = []
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        params.append(value)
    assignments.append("updated_at = ?")
    params.append(utcnow())
    params.append(record_id)
    with connect_state_db(config) as conn:
        conn.execute(f"UPDATE spam_quarantine_record SET {', '.join(assignments)} WHERE id = ?", tuple(params))
        return row_to_dict(conn.execute("SELECT * FROM spam_quarantine_record WHERE id = ?", (record_id,)).fetchone())


def list_runs(config, limit=50):
    initialize(config)
    with connect_state_db(config) as conn:
        return [
            row_to_dict(row)
            for row in conn.execute(
                "SELECT * FROM spam_scan_run ORDER BY started_at DESC, id DESC LIMIT ?",
                (int(limit),),
            )
        ]


def get_run(config, run_uuid):
    initialize(config)
    with connect_state_db(config) as conn:
        return row_to_dict(conn.execute("SELECT * FROM spam_scan_run WHERE uuid = ?", (run_uuid,)).fetchone())


def list_matches(config, run_uuid, limit=100):
    initialize(config)
    with connect_state_db(config) as conn:
        run = conn.execute("SELECT * FROM spam_scan_run WHERE uuid = ?", (run_uuid,)).fetchone()
        if not run:
            return None
        return [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT * FROM spam_scan_match
                WHERE run_id = ?
                ORDER BY classifier_score DESC, id
                LIMIT ?
                """,
                (run["id"], int(limit)),
            )
        ]


def list_review(config, statuses=None, limit=100):
    initialize(config)
    statuses = statuses or ["flagged", "quarantined"]
    placeholders = ",".join(["?"] * len(statuses))
    with connect_state_db(config) as conn:
        return [
            row_to_dict(row)
            for row in conn.execute(
                f"""
                SELECT * FROM spam_quarantine_record
                WHERE status IN ({placeholders})
                ORDER BY classifier_score DESC, id
                LIMIT ?
                """,
                tuple(statuses) + (int(limit),),
            )
        ]


def list_audit_actions(config, limit=100):
    initialize(config)
    with connect_state_db(config) as conn:
        return [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT history.*, record.uuid AS record_uuid,
                       record.namespace_name, record.repository_name
                FROM spam_action_history AS history
                LEFT JOIN spam_quarantine_record AS record
                    ON record.id = history.quarantine_record_id
                ORDER BY history.created_at DESC, history.id DESC
                LIMIT ?
                """,
                (int(limit),),
            )
        ]
