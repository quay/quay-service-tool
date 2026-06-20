from . import quay_db, store


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
        or "[removed by Quay spam detection review]"
    )

    with quay_db.write_db(config) as db:
        with db.atomic():
            updated = quay_db.update_repository_description(
                db,
                record["repository_id"],
                quarantine_description,
            )
            if updated != 1:
                raise RemediationError("repository row was not updated")

    return store.update_quarantine_record(
        config,
        record["id"],
        {"status": "quarantined", "quarantine_description": quarantine_description},
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
            updated = quay_db.update_repository_description(
                db,
                record["repository_id"],
                record.get("original_description"),
            )
            if updated != 1:
                raise RemediationError("repository row was not updated")

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
        redacted_description = ""

    with quay_db.write_db(config) as db:
        with db.atomic():
            updated = quay_db.update_repository_description(
                db,
                record["repository_id"],
                redacted_description,
            )
            if updated != 1:
                raise RemediationError("repository row was not updated")

    return store.update_quarantine_record(
        config,
        record["id"],
        {"status": "redacted", "redacted_description": redacted_description},
        "redact",
        operator=operator,
        details={"repository_id": record["repository_id"]},
    )
