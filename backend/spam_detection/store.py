from .database import (
    connect_state_db,
    ensure_policy,
    json_dumps,
    migrate_state_db,
    new_uuid,
    row_to_dict,
    utcnow,
)


def initialize(config):
    migrate_state_db(config)


def create_classifier(config, payload, operator=None):
    initialize(config)
    now = utcnow()
    feature_config = payload.get("feature_config") or {
        "token_pattern": r"[a-z0-9][a-z0-9_-]*",
        "include_repository_name": False,
    }
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
                float(payload.get("scan_threshold", 0.9)),
                float(payload.get("ingress_threshold", 0.9)),
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
        "scan_threshold",
        "ingress_threshold",
    ]:
        if key in payload:
            fields.append(f"{key} = ?")
            params.append(payload[key])
    if "enabled" in payload:
        fields.append("enabled = ?")
        params.append(1 if payload["enabled"] else 0)
    if "feature_config" in payload:
        fields.append("feature_config_json = ?")
        params.append(json_dumps(payload["feature_config"]))
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
                payload["text"],
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
        "scan_empty_repositories_only",
        "quarantine_description",
        "scan_dry_run",
        "max_repos",
        "batch_size",
        "sleep_between_batches",
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
            if key in ("include_private", "public_only_default", "scan_empty_repositories_only", "scan_dry_run"):
                value = 1 if value else 0
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
        cur = conn.execute(
            """
            INSERT INTO spam_scan_run (
                uuid, source, dry_run, status, started_at, classifier_snapshot_json,
                policy_snapshot_json, created_by
            ) VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
            """,
            (new_uuid(), source, 1 if dry_run else 0, now, json_dumps(classifier_snapshot), json_dumps(policy_snapshot), operator),
        )
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


def add_scan_match(config, run_id, repository, score, explanation):
    now = utcnow()
    excerpt = (repository.get("description") or "")[:500]
    with connect_state_db(config) as conn:
        cur = conn.execute(
            """
            INSERT INTO spam_scan_match (
                uuid, run_id, repository_id, namespace_name, repository_name,
                visibility, description_excerpt, classifier_score, explanation_json,
                is_empty, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                now,
            ),
        )
        return row_to_dict(conn.execute("SELECT * FROM spam_scan_match WHERE id = ?", (cur.lastrowid,)).fetchone())


def create_flagged_record(config, match, repository, classifier_snapshot):
    now = utcnow()
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
        cur = conn.execute(
            """
            INSERT INTO spam_quarantine_record (
                uuid, repository_id, namespace_name, repository_name, visibility,
                status, original_description, classifier_score,
                classifier_snapshot_json, run_id, match_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'flagged', ?, ?, ?, ?, ?, ?, ?)
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
                match["run_id"],
                match["id"],
                now,
                now,
            ),
        )
        record_id = cur.lastrowid
        conn.execute(
            "UPDATE spam_scan_match SET quarantine_record_id = ? WHERE id = ?",
            (record_id, match["id"]),
        )
        add_action_with_conn(conn, record_id, "flag", None, "flagged", None, {"match_uuid": match["uuid"]})
        return row_to_dict(
            conn.execute("SELECT * FROM spam_quarantine_record WHERE id = ?", (record_id,)).fetchone()
        )


def add_action_with_conn(conn, record_id, action, from_status, to_status, operator, details):
    conn.execute(
        """
        INSERT INTO spam_action_history (
            uuid, quarantine_record_id, action, from_status, to_status,
            operator, created_at, details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (new_uuid(), record_id, action, from_status, to_status, operator, utcnow(), json_dumps(details)),
    )


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


def update_quarantine_record(config, record_id, fields, action, operator=None, details=None):
    now = utcnow()
    with connect_state_db(config) as conn:
        current = conn.execute("SELECT * FROM spam_quarantine_record WHERE id = ?", (record_id,)).fetchone()
        if not current:
            return None
        assignments = []
        params = []
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            params.append(value)
        assignments.extend(["updated_at = ?", "actioned_by = ?", "actioned_at = ?"])
        params.extend([now, operator, now, record_id])
        conn.execute(f"UPDATE spam_quarantine_record SET {', '.join(assignments)} WHERE id = ?", tuple(params))
        updated = conn.execute("SELECT * FROM spam_quarantine_record WHERE id = ?", (record_id,)).fetchone()
        add_action_with_conn(
            conn,
            record_id,
            action,
            current["status"],
            updated["status"],
            operator,
            details or {},
        )
        return row_to_dict(updated)


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
