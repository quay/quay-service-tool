from . import DEFAULT_QUARANTINE_DESCRIPTION, quay_db, store


class RemediationError(Exception):
    pass


def _terminal_fields(config, record, description):
    return {
        "terminal_classifier_snapshot_json": (
            store.active_classifier_snapshot(config)
            or record.get("classifier_snapshot_json")
            or {}
        ),
        "terminal_description_fingerprint": store.description_fingerprint(description),
    }


def quarantine(config, record_uuid, operator=None):
    record = store.get_quarantine_record(config, record_uuid)
    if not record:
        raise RemediationError("quarantine record not found")
    if record["status"] != "flagged":
        raise RemediationError("only flagged records can be quarantined")

    policy = store.get_policy(config)
    quarantine_description = (
        record.get("quarantine_description")
        or policy.get("quarantine_description")
        or DEFAULT_QUARANTINE_DESCRIPTION
    )

    with quay_db.write_db(config) as db:
        with db.atomic():
            repository = quay_db.fetch_repository_for_remediation(db, record["repository_id"])
            if not repository:
                raise RemediationError("repository row was not found")
            if not repository["is_empty"]:
                raise RemediationError("only empty repositories can be quarantined")
            current_description = repository["description"]
            original_description = record.get("original_description")
            if current_description != quarantine_description:
                original_description = current_description
                store.update_quarantine_fields(
                    config,
                    record["id"],
                    {
                        "original_description": original_description,
                        "quarantine_description": quarantine_description,
                    },
                )
                updated = quay_db.update_repository_description_if_current(
                    db,
                    record["repository_id"],
                    quarantine_description,
                    current_description,
                )
                if updated != 1:
                    raise RemediationError("repository description changed during quarantine; refresh and retry")

    return store.update_quarantine_record(
        config,
        record["id"],
        {
            "status": "quarantined",
            "original_description": original_description,
            "quarantine_description": quarantine_description,
        },
        "quarantine",
        operator=operator,
        details={"repository_id": record["repository_id"]},
        training_feedback={"label": "spam", "text": original_description},
    )


def restore(config, record_uuid, operator=None):
    record = store.get_quarantine_record(config, record_uuid)
    if not record:
        raise RemediationError("quarantine record not found")
    if record["status"] != "quarantined":
        raise RemediationError("only quarantined records can be restored")

    with quay_db.write_db(config) as db:
        with db.atomic():
            current_description, found = quay_db.fetch_repository_description(db, record["repository_id"])
            if not found:
                raise RemediationError("repository row was not found")
            original_description = record.get("original_description")
            quarantine_description = record.get("quarantine_description")
            if current_description == original_description:
                pass
            elif current_description == quarantine_description:
                updated = quay_db.update_repository_description_if_current(
                    db,
                    record["repository_id"],
                    original_description,
                    current_description,
                )
                if updated != 1:
                    raise RemediationError("repository description changed during restore; refresh and retry")
            else:
                raise RemediationError("repository description no longer matches quarantine text; refresh and retry")

    fields = {"status": "restored"}
    fields.update(_terminal_fields(config, record, original_description))
    return store.update_quarantine_record(
        config,
        record["id"],
        fields,
        "restore",
        operator=operator,
        details={"repository_id": record["repository_id"]},
        training_feedback={"label": "ham", "text": original_description},
    )


def reopen(config, record_uuid, reason=None, operator=None):
    record = store.get_quarantine_record(config, record_uuid)
    if not record:
        raise RemediationError("quarantine record not found")
    if record["status"] != "restored":
        raise RemediationError("only restored records can be reopened")
    reason = (reason or "").strip()
    if not reason:
        raise RemediationError("reason is required")
    if len(reason) > 1000:
        raise RemediationError("reason must be 1000 characters or fewer")

    with quay_db.readonly_db(config) as db:
        repository = quay_db.fetch_repository_for_remediation(db, record["repository_id"])
    if not repository:
        raise RemediationError("repository row was not found")
    if repository["state"] != 0:
        raise RemediationError("repository is not active")
    if not repository["is_empty"]:
        raise RemediationError("only empty repositories can be reopened")

    fields = {
        "status": "flagged",
        "original_description": repository["description"],
        "description_fingerprint": store.description_fingerprint(repository["description"]),
        "classifier_snapshot_json": (
            store.active_classifier_snapshot(config)
            or record.get("classifier_snapshot_json")
            or {}
        ),
        "terminal_classifier_snapshot_json": None,
        "terminal_description_fingerprint": None,
    }
    try:
        return store.reopen_restored_record(
            config,
            record["id"],
            fields,
            operator,
            reason,
        )
    except ValueError as exc:
        raise RemediationError(str(exc)) from exc


def dismiss(config, record_uuid, operator=None):
    record = store.get_quarantine_record(config, record_uuid)
    if not record:
        raise RemediationError("quarantine record not found")
    if record["status"] not in ("flagged", "quarantined"):
        raise RemediationError("only flagged or quarantined records can be dismissed")
    with quay_db.readonly_db(config) as db:
        current_description, found = quay_db.fetch_repository_description(db, record["repository_id"])
        if not found:
            raise RemediationError("repository row was not found")
    reviewed_description = (
        record.get("original_description")
        if record["status"] == "quarantined"
        else current_description
    )
    fields = {"status": "dismissed"}
    fields.update(_terminal_fields(config, record, current_description))
    return store.update_quarantine_record(
        config,
        record["id"],
        fields,
        "dismiss",
        operator=operator,
        details={"repository_id": record["repository_id"]},
        training_feedback={"label": "ham", "text": reviewed_description},
    )


def redact(config, record_uuid, redacted_description=None, operator=None):
    record = store.get_quarantine_record(config, record_uuid)
    if not record:
        raise RemediationError("quarantine record not found")
    if record["status"] != "quarantined":
        raise RemediationError("only quarantined records can be redacted")
    if redacted_description is None:
        raise RemediationError("redacted_description is required")

    with quay_db.write_db(config) as db:
        with db.atomic():
            current_description, found = quay_db.fetch_repository_description(db, record["repository_id"])
            if not found:
                raise RemediationError("repository row was not found")
            quarantine_description = record.get("quarantine_description")
            if current_description == redacted_description:
                pass
            elif current_description == quarantine_description:
                updated = quay_db.update_repository_description_if_current(
                    db,
                    record["repository_id"],
                    redacted_description,
                    current_description,
                )
                if updated != 1:
                    raise RemediationError("repository description changed during redaction; refresh and retry")
            else:
                raise RemediationError("repository description no longer matches quarantine text; refresh and retry")

    fields = {"status": "redacted", "redacted_description": redacted_description}
    fields.update(_terminal_fields(config, record, redacted_description))
    return store.update_quarantine_record(
        config,
        record["id"],
        fields,
        "redact",
        operator=operator,
        details={"repository_id": record["repository_id"]},
        training_feedback={"label": "spam", "text": record.get("original_description")},
    )
