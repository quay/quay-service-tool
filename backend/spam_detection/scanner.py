import time

from . import classifier as classifier_lib
from . import quay_db, store
from .database import utcnow


class ScanError(Exception):
    pass


def _load_active(config, policy_override=None):
    policy = store.get_policy(config)
    if policy_override:
        policy.update(policy_override)
    classifier_id = policy.get("active_classifier_id")
    if not classifier_id:
        raise ScanError("spam detection policy has no active classifier")
    classifier = store.get_classifier_by_id(config, classifier_id)
    if not classifier:
        raise ScanError("active classifier was not found")
    artifact = classifier_lib.load_artifact_from_classifier(classifier)
    return classifier, artifact, policy


def preview(config, policy_override=None, limit=100):
    classifier, artifact, policy = _load_active(config, policy_override)
    include_private = bool(policy.get("include_private"))
    empty_only = bool(policy.get("scan_empty_repositories_only"))
    batch_size = min(int(policy.get("batch_size") or 200), int(limit))
    threshold = float(policy.get("scan_threshold") or classifier["scan_threshold"])
    scanned = 0
    matched = []
    last_seen_id = 0

    with quay_db.readonly_db(config) as db:
        while len(matched) < limit:
            repositories = quay_db.fetch_repository_batch(
                db,
                last_seen_id=last_seen_id,
                batch_size=batch_size,
                include_private=include_private,
                empty_only=empty_only,
            )
            if not repositories:
                break
            for repository in repositories:
                last_seen_id = max(last_seen_id, int(repository["id"]))
                scanned += 1
                decision = classifier_lib.classify_text(
                    artifact,
                    repository.get("description"),
                    repository.get("repository_name"),
                    repository.get("visibility"),
                )
                if decision["score"] >= threshold:
                    matched.append(
                        {
                            "repository_id": repository["id"],
                            "namespace_name": repository["namespace_name"],
                            "repository_name": repository["repository_name"],
                            "visibility": repository.get("visibility"),
                            "description_excerpt": (repository.get("description") or "")[:500],
                            "classifier_score": decision["score"],
                            "explanation": decision["explanation"],
                            "is_empty": bool(repository.get("is_empty")),
                        }
                    )
                    if len(matched) >= limit:
                        break
    return {
        "classifier": classifier,
        "policy": policy,
        "repos_scanned": scanned,
        "repos_matched": len(matched),
        "matches": matched,
    }


def run_scan(config, source="manual", dry_run=None, max_repos=None, operator=None):
    classifier, artifact, policy = _load_active(config)
    scan_dry_run = bool(policy.get("scan_dry_run")) if dry_run is None else bool(dry_run)
    threshold = float(policy.get("scan_threshold") or classifier["scan_threshold"])
    include_private = bool(policy.get("include_private"))
    empty_only = bool(policy.get("scan_empty_repositories_only"))
    batch_size = int(policy.get("batch_size") or config.get("SPAM_DETECTION_BATCH_SIZE", 200))
    sleep_between_batches = float(
        policy.get("sleep_between_batches")
        if policy.get("sleep_between_batches") is not None
        else config.get("SPAM_DETECTION_SLEEP_BETWEEN_BATCHES", 0.5)
    )
    max_repos = int(max_repos if max_repos is not None else policy.get("max_repos") or 0)

    run = store.create_scan_run(config, source, scan_dry_run, artifact, policy, operator=operator)
    counters = {
        "repos_scanned": 0,
        "repos_matched": 0,
        "repos_flagged": 0,
        "repos_quarantined": 0,
    }
    last_seen_id = 0

    try:
        with quay_db.readonly_db(config) as db:
            while True:
                page_size = batch_size
                if max_repos:
                    remaining = max_repos - counters["repos_scanned"]
                    if remaining <= 0:
                        break
                    page_size = min(page_size, remaining)

                repositories = quay_db.fetch_repository_batch(
                    db,
                    last_seen_id=last_seen_id,
                    batch_size=page_size,
                    include_private=include_private,
                    empty_only=empty_only,
                )
                if not repositories:
                    break

                for repository in repositories:
                    last_seen_id = max(last_seen_id, int(repository["id"]))
                    counters["repos_scanned"] += 1
                    decision = classifier_lib.classify_text(
                        artifact,
                        repository.get("description"),
                        repository.get("repository_name"),
                        repository.get("visibility"),
                    )
                    if decision["score"] < threshold:
                        continue
                    counters["repos_matched"] += 1
                    match = store.add_scan_match(
                        config,
                        run["id"],
                        repository,
                        decision["score"],
                        decision["explanation"],
                    )
                    if not scan_dry_run:
                        store.create_flagged_record(config, match, repository, artifact)
                        counters["repos_flagged"] += 1

                if sleep_between_batches:
                    time.sleep(sleep_between_batches)

        store.update_scan_run(
            config,
            run["id"],
            status="completed",
            completed_at=utcnow(),
            **counters,
        )
    except Exception as exc:
        store.update_scan_run(
            config,
            run["id"],
            status="failed",
            completed_at=utcnow(),
            error=str(exc),
            **counters,
        )
        raise

    return store.get_run(config, run["uuid"])
