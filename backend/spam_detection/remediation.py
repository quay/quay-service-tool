from . import DEFAULT_QUARANTINE_DESCRIPTION, quay_db, store


class RemediationError(Exception):
    pass


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
            current_description, found = quay_db.fetch_repository_description(db, record["repository_id"])
            if not found:
                raise RemediationError("repository row was not found")
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

    return store.update_quarantine_record(
        config,
        record["id"],
        {"status": "restored"},
        "restore",
        operator=operator,
        details={"repository_id": record["repository_id"]},
    )


def dismiss(config, record_uuid, operator=None):
    record = store.get_quarantine_record(config, record_uuid)
    if not record:
        raise RemediationError("quarantine record not found")
    if record["status"] not in ("flagged", "quarantined"):
        raise RemediationError("only flagged or quarantined records can be dismissed")
    return store.update_quarantine_record(
        config,
        record["id"],
        {"status": "dismissed"},
        "dismiss",
        operator=operator,
        details={"repository_id": record["repository_id"]},
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

    return store.update_quarantine_record(
        config,
        record["id"],
        {"status": "redacted", "redacted_description": redacted_description},
        "redact",
        operator=operator,
        details={"repository_id": record["repository_id"]},
    )
