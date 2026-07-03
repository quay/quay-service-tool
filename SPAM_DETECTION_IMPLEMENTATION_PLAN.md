# Quay Spam Detection and Quarantine Implementation Plan

## Reviewed Context

This plan is aligned with:

* `quay/enhancements#42`, which assigns classifier configuration, training
  examples, model generation, scan execution, run history, match records,
  quarantine state, review workflows, remediation history, and redaction
  history to `quay-service-tool`.
* `quay/quay#6154`, which limits Quay runtime behavior to repository
  description ingress evaluation using a local JSON Bayesian classifier
  artifact.
* `michaelalang/spam-classifications`, which is useful as seed-data and
  training-flow prior art but must not become a Quay runtime dependency.

Important boundary decisions for this repository:

* Quay must not call `quay-service-tool` on the request path.
* `quay-service-tool` generates a versioned JSON artifact for the Quay image
  build to bake into the image.
* Broad scans read directly from the Quay database through a read-only user or
  replica, with a read-only session enabled where the database supports it.
* Approved quarantine, restore, and redaction use explicit direct Quay database
  writes, not user-scoped Quay repository APIs.
* Remediation must use conditional writes and retry-safe service-tool state
  updates because the Quay DB and service-tool state DB do not share one ACID
  transaction.
* Initial auditability is through service-tool logs and service-tool state, not
  a new Quay audit API.

## Current Repository Shape

The service tool currently has a small Flask-RESTful backend and PatternFly
frontend:

* Backend tasks live under `backend/tasks/` and are registered in
  `backend/app.py`.
* Existing endpoints use `@login_required`, `@verify_admin_permissions` or
  related decorators, and `@log_response` from `backend/utils.py`.
* The backend configures Quay's Peewee database from `DB_URI` at startup.
* There is no service-tool-owned durable state database or migration framework
  in the repository today.
* Frontend routes are declared in `frontend/src/app/routes.tsx` and use
  role-gated navigation in `frontend/src/app/AppLayout/AppLayout.tsx`.
* API calls use `frontend/src/services/HttpService.tsx`.

The implementation therefore needs to add service-tool state and migrations
before adding scan history, classifier history, or quarantine workflows.

## Artifact Contract With Quay

The generated classifier artifact must be JSON and compatible with the Quay
local reader from `quay/quay#6154`. The initial service-tool trainer should
emit at least:

```json
{
  "version": "2026-06-20.1",
  "spam_prior": 0.5,
  "ham_prior": 0.5,
  "token_spam_counts": {},
  "token_ham_counts": {},
  "spam_token_total": 0,
  "ham_token_total": 0,
  "vocabulary_size": 1,
  "smoothing": 1.0,
  "ingress_threshold": 0.9,
  "ingress_thresholds": {
    "public": 0.9,
    "private": 0.98
  },
  "feature_config": {
    "token_pattern": "[a-z0-9][a-z0-9_-]*",
    "include_repository_name": false
  },
  "training_corpus_version": "..."
}
```

The trainer also writes a sidecar checksum file or API response field containing
the SHA256 of the exact JSON bytes. Quay loads the baked JSON artifact from
`/conf/spam-detection/classifier.json` by default and verifies
`SPAM_DETECTION_CLASSIFIER_VERSION` and optionally
`SPAM_DETECTION_CLASSIFIER_SHA256`.

The active service-tool policy is the source of truth for the ingress threshold
embedded in the artifact. Training and artifact export must write a new
versioned artifact when the active policy threshold changes, so Quay never has
to consult service-tool on the request path.

For production handoff, service-tool must support exporting an additional copy
of the artifact to an explicit build output path. The Quay image build copies
that JSON file and its `.sha256` sidecar into the image at
`/conf/spam-detection/classifier.json`. The initial implementation should not
require runtime artifact downloads, shared mutable volumes, or calls from Quay
pods to service-tool.

## Proposed Backend Layout

Add these backend modules:

* `backend/spam_detection/`
  * `__init__.py`
  * `models.py` for service-tool-owned Peewee models.
  * `database.py` for the service-tool state DB connection and migration
    helpers.
  * `migrations.py` for idempotent schema creation or a small migration runner.
  * `classifier.py` for tokenization, training, artifact serialization,
    artifact loading, scoring, and explanations.
  * `training_import.py` for reviewed-label and seed CSV import.
  * `quay_db.py` for explicit read-only and write-capable Quay DB connection
    helpers, including session-level read-only protection for scan/preview
    connections where supported.
  * `scanner.py` for cursor-paginated repository scans.
  * `remediation.py` for quarantine, restore, dismiss, and redact state
    transitions and Quay DB mutations.
  * `schemas.py` for request validation and response shaping.
* `backend/tasks/spam_detection.py` for Flask-RESTful resources.
* `backend/cli.py` or `backend/spam_detection_cli.py` for command-line entry
  points used by CronJobs and operators.

Register resources in `backend/app.py`:

* `GET /spam-detection/health`
* `GET /spam-detection/classifiers`
* `POST /spam-detection/classifiers`
* `PUT /spam-detection/classifiers/<uuid>`
* `POST /spam-detection/classifiers/<uuid>/training-examples`
* `POST /spam-detection/classifiers/<uuid>/import-csv`
* `POST /spam-detection/classifiers/<uuid>/train`
* `POST /spam-detection/classifiers/<uuid>/export-artifact`
* `GET /spam-detection/policy`
* `PUT /spam-detection/policy`
* `POST /spam-detection/preview`
* `POST /spam-detection/runs`
* `GET /spam-detection/runs`
* `GET /spam-detection/runs/<uuid>/matches`
* `GET /spam-detection/review`
* `POST /spam-detection/review/<uuid>/quarantine`
* `POST /spam-detection/review/<uuid>/restore`
* `POST /spam-detection/review/<uuid>/dismiss`
* `POST /spam-detection/review/<uuid>/redact`

## Configuration

Extend `backend/config/config.yaml` and app startup handling with:

* `SPAM_DETECTION_STATE_DB_URI`: service-tool-owned state database.
* `SPAM_DETECTION_READONLY_DB_URI`: read-only Quay user or replica for preview,
  scans, run-history enrichment, and training candidates.
* `SPAM_DETECTION_WRITE_DB_URI`: write-capable Quay DB path for approved
  quarantine, restore, and redaction.
* `SPAM_DETECTION_ARTIFACT_DIR`: output directory for generated JSON artifacts.
* `SPAM_DETECTION_BATCH_SIZE`: default `200`.
* `SPAM_DETECTION_SLEEP_BETWEEN_BATCHES`: default `0.5`.
* `SPAM_DETECTION_SCAN_DRY_RUN`: default `true`.
* `SPAM_DETECTION_MAX_REPOS`: default `0` for unlimited.
* `SPAM_DETECTION_INCLUDE_PRIVATE`: default `false`.
* `SPAM_DETECTION_QUARANTINE_DESCRIPTION`: standard quarantine notice that tells
  repository owners spam detection removed the description, gives the restore
  contact path, states owner remediation expectations, and names the expected
  review timeline.
* `SPAM_DETECTION_ROLE`: read/report/preview access.
* `SPAM_DETECTION_REMEDIATION_ROLE`: write/remediation access.

Do not swap Quay's global Peewee connection between replica and primary during
requests. Use separate connection objects or direct SQL helpers for spam
detection read/write paths.

## Service-Tool State Model

Implement service-tool-owned tables. These are not Quay application tables.

### `spam_classifier`

* `id`
* `uuid`
* `name`
* `enabled`
* `training_corpus_version`
* `artifact_version`
* `artifact_sha256`
* `artifact_path`
* `model_snapshot_json`
* `feature_config_json`
* `scan_threshold`
* `ingress_threshold`: default threshold used when training/exporting outside
  the active policy.
* `created_at`
* `updated_at`
* `created_by`
* `updated_by`

Indexes:

* `enabled, updated_at`
* unique `uuid`
* unique nullable `artifact_version`

### `spam_training_example`

* `id`
* `uuid`
* `classifier_id`
* `repository_id`
* `namespace_name`
* `repository_name`
* `text`
* `label`: `spam` or `ham`
* `source`: `manual_review`, `quarantine`, `restore`, `dismiss`, `redaction`,
  `csv_import`, `seed_import`
* `source_ref`
* `created_by`
* `created_at`

Indexes:

* `classifier_id, label, created_at`
* `source, created_at`
* `repository_id, created_at`

### `spam_policy`

* `id`
* `uuid`
* `active_classifier_id`
* `scan_threshold`
* `ingress_threshold`: source of truth for active Quay ingress artifacts.
* `include_private`
* `public_only_default`
* `scan_empty_repositories_only`
* `scan_filters_json`
* `quarantine_description`
* `scan_dry_run`
* `max_repos`
* `batch_size`
* `sleep_between_batches`
* `created_at`
* `updated_at`
* `updated_by`

Keep a single active policy initially. Store complete snapshots on runs and
actions so historical decisions remain explainable.

### `spam_scan_run`

* `id`
* `uuid`
* `source`: `manual`, `cronjob`, or `cli`
* `dry_run`
* `status`: `running`, `completed`, or `failed`
* `started_at`
* `completed_at`
* `classifier_snapshot_json`
* `policy_snapshot_json`
* `repos_scanned`
* `repos_matched`
* `repos_flagged`
* `repos_quarantined`
* `error`
* `created_by`

Indexes:

* `started_at`
* `status, started_at`

### `spam_scan_match`

* `id`
* `uuid`
* `run_id`
* `repository_id`
* `namespace_name`
* `repository_name`
* `visibility`
* `description_excerpt`
* `classifier_score`
* `explanation_json`
* `is_empty`
* `quarantine_record_id`
* `created_at`

Indexes:

* `run_id, classifier_score, id`
* `repository_id, created_at`

### `spam_quarantine_record`

* `id`
* `uuid`
* `repository_id`
* `namespace_name`
* `repository_name`
* `visibility`
* `status`: `flagged`, `quarantined`, `restored`, `dismissed`, or `redacted`
* `original_description`
* `quarantine_description`
* `redacted_description`
* `classifier_score`
* `classifier_snapshot_json`
* `run_id`
* `match_id`
* `created_at`
* `updated_at`
* `actioned_by`
* `actioned_at`

Indexes:

* `status, classifier_score, id`
* `repository_id, status`

Application validation must prevent more than one active `flagged` or
`quarantined` record for the same repository.

### `spam_action_history`

* `id`
* `uuid`
* `quarantine_record_id`
* `action`: `flag`, `quarantine`, `restore`, `dismiss`, `redact`,
  `train`, `import`, `policy_update`, `artifact_export`
* `from_status`
* `to_status`
* `operator`
* `created_at`
* `details_json`

Indexes:

* `quarantine_record_id, created_at`
* `action, created_at`

## Training Implementation

Use an in-repository lightweight multinomial naive Bayes trainer rather than
adding a runtime classifier service. Avoid adding scikit-learn to Quay or to
the generated artifact contract.

Training flow:

1. Load approved `spam_training_example` rows for the selected classifier.
2. Optionally import seed CSV files shaped as `text,label`, including
   `michaelalang/spam-classifications` CSV exports.
3. Validate labels as `spam` or `ham`.
4. Tokenize with the same configurable regex that Quay uses by default.
5. Count spam and ham tokens.
6. Compute spam and ham priors from example counts.
7. Store model snapshot metadata in service-tool state.
8. Write canonical JSON with deterministic key ordering to
   `SPAM_DETECTION_ARTIFACT_DIR`.
9. Compute SHA256 over the exact bytes written.
10. Record an `artifact_export` action-history row.

The first implementation should include repository description text only by
default. Optional repository-name tokens can be controlled by
`feature_config.include_repository_name`. The tokenizer regex should remain the
fixed reviewed default until a regex safety strategy suitable for Quay's
request path is available.

## Scanning Implementation

Scanning must read from the Quay DB directly, not from Quay APIs.

Query shape:

```sql
SELECT ...
FROM repository ...
WHERE repository.id > :last_seen_id
ORDER BY repository.id
LIMIT :batch_size
```

Rules:

* Default scan scope is public repository descriptions only.
* Private repositories are excluded unless `SPAM_DETECTION_INCLUDE_PRIVATE` or
  the policy draft explicitly enables private scanning.
* Use cursor-based pagination over repository IDs.
* Avoid offset pagination.
* Avoid per-repository tag queries; prefetch emptiness/tag-existence for the
  current batch.
* Persist `spam_scan_run` and `spam_scan_match` rows for scans.
* Preview uses the same read path and classifier but does not persist run,
  match, or quarantine rows.
* Dry-run scans persist run and match history but do not open quarantine records
  and do not mutate Quay data.
* Non-dry-run scans may open `flagged` review records but still require human
  approval for quarantine, restore, dismiss, and redaction.

The exact repository visibility join must be validated against the Quay models
available through the pinned `quay` dependency before implementation. If model
APIs are awkward for separate read/write connections, use narrow parameterized
SQL and keep it isolated in `backend/spam_detection/quay_db.py`.

## Remediation Implementation

Remediation is state-machine driven and transactional.

Allowed lifecycle:

* `flagged` -> `quarantined`
* `flagged` -> `dismissed`
* `quarantined` -> `restored`
* `quarantined` -> `dismissed`
* `quarantined` -> `redacted`

Quarantine:

1. Open a service-tool state transaction.
2. Lock or refresh the quarantine record.
3. Validate status is `flagged`.
4. Open a write-capable Quay DB transaction.
5. Re-read the Quay repository row by `repository_id`.
6. Preserve the latest original description if not already preserved.
7. Write the configured quarantine description directly to the Quay repository
   row.
8. Commit Quay write, then update service-tool status and action history.
9. Log operator, repository ID, namespace/name, previous status, new status,
   and classifier score.

Restore:

* Require status `quarantined`.
* Write `original_description` back to the Quay repository row.
* Mark service-tool state `restored`.
* Add action history and log entry.

Dismiss:

* Allow from `flagged` or `quarantined`.
* Do not mutate Quay data.
* Mark service-tool state `dismissed`.
* Add action history and log entry.

Redact:

* Require status `quarantined`.
* Write an explicit redacted description or `NULL`, depending on policy.
* Mark service-tool state `redacted`.
* Preserve action history but treat content restoration as intentionally no
  longer available through the normal restore action.

Because a single ACID transaction cannot reliably span two different database
connections, implementation should make operations idempotent and record enough
state to safely retry or reconcile if the service-tool state update fails after
the Quay write succeeds.

## CLI Commands

Add command-line entry points that can run inside the service-tool image:

* `uv run python -m spam_detection_cli migrate`
* `uv run python -m spam_detection_cli import-csv --classifier <uuid> --path <csv> --source seed_import`
* `uv run python -m spam_detection_cli train --classifier <uuid> --artifact-version <version>`
* `uv run python -m spam_detection_cli export-artifact --classifier <uuid>`
* `uv run python -m spam_detection_cli export-artifact --classifier <uuid> --output-path <quay-build-context>/spam-classifier.json`
* `uv run python -m spam_detection_cli scan --source cronjob --dry-run`
* `uv run python -m spam_detection_cli scan --source manual --max-repos <n>`
* `uv run python -m spam_detection_cli healthcheck`

The scheduled scan path should be an OpenShift CronJob invoking the CLI scan
entry point, not a Quay worker and not an always-running scanner in each Quay
pod.

Manual scans started through the service-tool API must be bounded by
`SPAM_DETECTION_API_SCAN_LIMIT`; unbounded production scans should use the CLI
or scheduled CronJob path.

## Frontend Plan

Add:

* `frontend/src/app/SpamDetection/SpamDetection.tsx`
* `frontend/src/app/SpamDetection/SpamDetection.test.tsx`
* optional small child components for classifier, policy, preview, runs, and
  review queue sections.

Register a route in `frontend/src/app/routes.tsx`:

* label: `Spam Detection`
* path: `/spam-detection`
* permission: `window.SPAM_DETECTION_ROLE || process.env.SPAM_DETECTION_ROLE`

Render `SPAM_DETECTION_ROLE` and `SPAM_DETECTION_REMEDIATION_ROLE` through
`backend/app.py` and `backend/templates/index.html`.

Initial UI sections:

* Classifier: list classifiers, thresholds, artifact version, SHA, train/export
  actions.
* Policy: edit scan threshold, ingress threshold, public/private handling,
  dry-run, max repos, batch size, and quarantine notice.
* Preview: run a read-only preview with filters and paginated matches.
* Runs: list scan runs and drill into matches.
* Review Queue: filter flagged/quarantined records and run quarantine, restore,
  dismiss, or redact actions with confirmation.

## Tests

Backend tests:

* state DB migration/schema creation and indexes;
* classifier training from manual examples;
* seed CSV import with `text,label` rows;
* deterministic artifact JSON and SHA256;
* artifact compatibility with Quay #6154 expected fields;
* preview does not write run, match, quarantine, or Quay repository rows;
* scans use cursor pagination and public-only default;
* private repositories are skipped unless explicitly enabled;
* dry-run scan persists run/match rows without quarantine records;
* non-dry-run scan opens flagged records but does not mutate Quay content;
* invalid review lifecycle transitions fail;
* quarantine/restore/redact use write DB helper and update state history;
* remediation role gating differs from read/preview role gating;
* healthcheck reports state DB, read-only Quay DB, and write DB status.

Frontend tests:

* route visibility by spam detection role;
* classifier list and train/export states;
* policy editing and validation;
* preview loading, error, empty, and result states;
* run history and match drilldown;
* review action confirmation and API errors.

## Implementation Order

1. Add service-tool spam detection config keys, roles, and health surface.
2. Add service-tool state DB connection and migration runner.
3. Add service-tool state models and unit tests.
4. Add classifier training, CSV import, artifact export, and tests.
5. Add read-only Quay DB scan query helpers and preview API.
6. Add scan runner, scan CLI, run/match persistence, and tests.
7. Add remediation state machine and direct write DB helpers.
8. Add review APIs and role gates.
9. Add frontend route and the initial classifier/policy/preview/runs/review
   views.
10. Add deployment notes for the CronJob and artifact distribution to Quay.

## Resolved Decisions

* Service-tool-owned spam detection state uses `SPAM_DETECTION_STATE_DB_URI`.
* Approved quarantine replaces `Repository.description` with the configured
  standard quarantine notice.
* The first implementation includes backend APIs, CLI commands, and the
  PatternFly operator UI.
* Public/private scanning uses Quay's `repository.visibility_id` to
  `visibility.name` relationship.
* Generated classifier artifacts are exported as JSON plus `.sha256` sidecar
  files for the Quay image build to bake into the image.
