import json
import logging
import os

from flask import current_app, make_response, request, send_file
from flask_login import current_user, login_required
from flask_restful import Resource

from spam_detection import classifier, quay_db, remediation, scanner, store, training_import
from spam_detection.database import migrate_state_db, state_db_uri
from utils import (
    log_response,
    verify_spam_detection_read_permissions,
    verify_spam_detection_write_permissions,
)


logger = logging.getLogger(__name__)


def _operator():
    return getattr(current_user, "email", None) or getattr(current_user, "username", None)


def _json_response(payload, status=200):
    return make_response(json.dumps(payload), status)


def _body():
    return request.get_json(silent=True) or {}


def _bounded_limit(raw_value, default, maximum, field="limit"):
    value = int(raw_value if raw_value is not None else default)
    if value <= 0:
        raise ValueError(f"{field} must be greater than 0")
    if value > maximum:
        raise ValueError(f"{field} must be less than or equal to {maximum}")
    return value


def _scan_limit(raw_value, default, maximum):
    value = raw_value if raw_value is not None else default
    if isinstance(value, str) and value.strip().lower() in ("all", "unbounded"):
        return 0
    value = int(value)
    if value < 0:
        raise ValueError("max_repos must be 0 or greater")
    if value and maximum > 0 and value > maximum:
        raise ValueError(f"max_repos must be less than or equal to {maximum}, or 0 for all")
    return value


class SpamDetectionHealthTask(Resource):
    @log_response
    @verify_spam_detection_read_permissions
    @login_required
    def get(self):
        config = current_app.config
        status = {
            "state_db_uri": state_db_uri(config),
            "state_db": "unknown",
            "readonly_quay_db": "unknown",
            "write_quay_db": "unknown",
        }
        http_status = 200
        try:
            migrate_state_db(config)
            status["state_db"] = "ok"
        except Exception as exc:
            logger.exception("Spam detection state DB healthcheck failed")
            status["state_db"] = str(exc)
            http_status = 503

        for key, label in [
            ("SPAM_DETECTION_READONLY_DB_URI", "readonly_quay_db"),
            ("SPAM_DETECTION_WRITE_DB_URI", "write_quay_db"),
        ]:
            uri = config.get(key)
            try:
                quay_db.check_connection(uri, read_only=key == "SPAM_DETECTION_READONLY_DB_URI")
                status[label] = "ok"
            except Exception as exc:
                logger.exception("Spam detection %s healthcheck failed", label)
                status[label] = str(exc)
                http_status = 503

        return _json_response(status, http_status)


class SpamClassifierListTask(Resource):
    @log_response
    @verify_spam_detection_read_permissions
    @login_required
    def get(self):
        return _json_response({"classifiers": store.list_classifiers(current_app.config)})

    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self):
        payload = _body()
        if not payload.get("name"):
            return _json_response({"message": "name is required"}, 400)
        try:
            created = store.create_classifier(current_app.config, payload, operator=_operator())
            return _json_response({"classifier": created}, 201)
        except Exception as exc:
            logger.exception("Unable to create spam classifier")
            return _json_response({"message": str(exc)}, 500)


class SpamClassifierImportArtifactTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self):
        upload = request.files.get("artifact")
        name = (request.form.get("name") or "").strip()
        enabled = (request.form.get("enabled") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if not upload or not name:
            return _json_response({"message": "name and artifact file are required"}, 400)
        try:
            max_bytes = int(
                current_app.config.get(
                    "SPAM_DETECTION_MAX_ARTIFACT_BYTES",
                    classifier.DEFAULT_MAX_ARTIFACT_BYTES,
                )
            )
            content = upload.stream.read(max_bytes + 1)
            imported, created = classifier.import_classifier_artifact(
                current_app.config,
                name,
                content,
                enabled=enabled,
                operator=_operator(),
            )
            store.add_action(
                current_app.config,
                None,
                "artifact_import",
                None,
                None,
                operator=_operator(),
                details={
                    "classifier_uuid": imported["uuid"],
                    "artifact_version": imported["artifact_version"],
                    "artifact_sha256": imported["artifact_sha256"],
                    "created": created,
                    "activated": enabled,
                },
            )
            return _json_response(
                {
                    "classifier": imported,
                    "created": created,
                    "imported_artifact_version": (
                        imported.get("base_artifact_version")
                        or imported["artifact_version"]
                    ),
                },
                201 if created else 200,
            )
        except classifier.ClassifierError as exc:
            return _json_response({"message": str(exc)}, 400)
        except Exception as exc:
            logger.exception("Unable to import spam classifier artifact")
            return _json_response({"message": str(exc)}, 500)


class SpamClassifierTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def put(self, classifier_uuid):
        try:
            updated = store.update_classifier(
                current_app.config,
                classifier_uuid,
                _body(),
                operator=_operator(),
            )
            if not updated:
                return _json_response({"message": "classifier not found"}, 404)
            return _json_response({"classifier": updated})
        except ValueError as exc:
            return _json_response({"message": str(exc)}, 400)
        except Exception as exc:
            logger.exception("Unable to update spam classifier")
            return _json_response({"message": str(exc)}, 500)


class SpamTrainingExamplesTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, classifier_uuid):
        payload = _body()
        if not payload.get("text") or not payload.get("label"):
            return _json_response({"message": "text and label are required"}, 400)
        try:
            example = store.add_training_example(
                current_app.config,
                classifier_uuid,
                payload,
                operator=_operator(),
            )
            if not example:
                return _json_response({"message": "classifier not found"}, 404)
            return _json_response({"training_example": example}, 201)
        except ValueError as exc:
            return _json_response({"message": str(exc)}, 400)
        except Exception as exc:
            logger.exception("Unable to add spam training example")
            return _json_response({"message": str(exc)}, 500)


class SpamClassifierImportCsvTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, classifier_uuid):
        payload = _body()
        path = payload.get("path")
        if not path:
            return _json_response({"message": "path is required"}, 400)
        try:
            result = training_import.import_csv(
                current_app.config,
                classifier_uuid,
                path,
                source=payload.get("source", "seed_import"),
                operator=_operator(),
            )
            return _json_response(result, 201)
        except ValueError as exc:
            return _json_response({"message": str(exc)}, 400)
        except Exception as exc:
            logger.exception("Unable to import spam training CSV")
            return _json_response({"message": str(exc)}, 500)


class SpamClassifierTrainTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, classifier_uuid):
        try:
            updated = classifier.train_classifier(
                current_app.config,
                classifier_uuid,
                artifact_version=_body().get("artifact_version"),
            )
            store.add_action(
                current_app.config,
                None,
                "train",
                None,
                None,
                operator=_operator(),
                details={"classifier_uuid": classifier_uuid},
            )
            return _json_response({"classifier": updated})
        except classifier.ClassifierError as exc:
            return _json_response({"message": str(exc)}, 400)
        except Exception as exc:
            logger.exception("Unable to train spam classifier")
            return _json_response({"message": str(exc)}, 500)


class SpamClassifierExportArtifactTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, classifier_uuid):
        try:
            updated = classifier.export_artifact(
                current_app.config,
                classifier_uuid,
                artifact_version=_body().get("artifact_version"),
                output_path=_body().get("output_path"),
            )
            store.add_action(
                current_app.config,
                None,
                "artifact_export",
                None,
                None,
                operator=_operator(),
                details={"classifier_uuid": classifier_uuid},
            )
            return _json_response({"classifier": updated})
        except classifier.ClassifierError as exc:
            return _json_response({"message": str(exc)}, 400)
        except Exception as exc:
            logger.exception("Unable to export spam classifier artifact")
            return _json_response({"message": str(exc)}, 500)


class SpamClassifierArtifactTask(Resource):
    @log_response
    @verify_spam_detection_read_permissions
    @login_required
    def get(self, classifier_uuid):
        configured = store.get_classifier(current_app.config, classifier_uuid)
        if not configured:
            return _json_response({"message": "classifier not found"}, 404)
        artifact_path = configured.get("artifact_path")
        if not artifact_path or not os.path.isfile(artifact_path):
            return _json_response({"message": "classifier has no generated artifact"}, 404)
        version = configured.get("artifact_version") or "unversioned"
        return send_file(
            artifact_path,
            mimetype="application/json",
            as_attachment=True,
            download_name=f"quay-spam-classifier-{version}.json",
        )


class SpamClassifierPromoteArtifactTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, classifier_uuid):
        try:
            promoted = classifier.promote_artifact(current_app.config, classifier_uuid)
            configured = promoted["classifier"]
            store.add_action(
                current_app.config,
                None,
                "artifact_promote",
                None,
                None,
                operator=_operator(),
                details={
                    "classifier_uuid": classifier_uuid,
                    "artifact_version": configured.get("artifact_version"),
                    "artifact_sha256": promoted["promoted_sha256"],
                    "destination": promoted["promoted_path"],
                },
            )
            return _json_response(promoted)
        except classifier.ClassifierError as exc:
            return _json_response({"message": str(exc)}, 400)
        except Exception as exc:
            logger.exception("Unable to promote spam classifier artifact")
            return _json_response({"message": str(exc)}, 500)


class SpamPolicyTask(Resource):
    @log_response
    @verify_spam_detection_read_permissions
    @login_required
    def get(self):
        return _json_response({"policy": store.get_policy(current_app.config)})

    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def put(self):
        try:
            updated = store.update_policy(current_app.config, _body(), operator=_operator())
            store.add_action(
                current_app.config,
                None,
                "policy_update",
                None,
                None,
                operator=_operator(),
                details={"policy_uuid": updated.get("uuid")},
            )
            return _json_response({"policy": updated})
        except ValueError as exc:
            return _json_response({"message": str(exc)}, 400)
        except Exception as exc:
            logger.exception("Unable to update spam policy")
            return _json_response({"message": str(exc)}, 500)


class SpamPreviewTask(Resource):
    @log_response
    @verify_spam_detection_read_permissions
    @login_required
    def post(self):
        payload = _body()
        try:
            limit = _bounded_limit(payload.get("limit"), 100, 500)
            result = scanner.preview(
                current_app.config,
                policy_override=payload.get("policy"),
                limit=limit,
            )
            return _json_response(result)
        except ValueError as exc:
            return _json_response({"message": str(exc)}, 400)
        except Exception as exc:
            logger.exception("Unable to preview spam classifier")
            return _json_response({"message": str(exc)}, 500)


class SpamRunsTask(Resource):
    @log_response
    @verify_spam_detection_read_permissions
    @login_required
    def get(self):
        try:
            limit = _bounded_limit(request.args.get("limit"), 50, 500)
            return _json_response({"runs": store.list_runs(current_app.config, limit=limit)})
        except ValueError as exc:
            return _json_response({"message": str(exc)}, 400)

    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self):
        payload = _body()
        try:
            api_limit = int(current_app.config.get("SPAM_DETECTION_API_SCAN_LIMIT", 10000))
            configured_max = int(current_app.config.get("SPAM_DETECTION_MAX_REPOS") or 0)
            requested_max = payload.get("max_repos")
            max_repos = _scan_limit(
                requested_max,
                configured_max,
                api_limit,
            )
            run = scanner.run_scan(
                current_app.config,
                source=payload.get("source", "manual"),
                dry_run=payload.get("dry_run"),
                max_repos=max_repos,
                operator=_operator(),
            )
            return _json_response({"run": run}, 201)
        except ValueError as exc:
            return _json_response({"message": str(exc)}, 400)
        except Exception as exc:
            logger.exception("Unable to run spam scan")
            return _json_response({"message": str(exc)}, 500)


class SpamRunMatchesTask(Resource):
    @log_response
    @verify_spam_detection_read_permissions
    @login_required
    def get(self, run_uuid):
        try:
            limit = _bounded_limit(request.args.get("limit"), 100, 500)
        except ValueError as exc:
            return _json_response({"message": str(exc)}, 400)
        matches = store.list_matches(current_app.config, run_uuid, limit=limit)
        if matches is None:
            return _json_response({"message": "run not found"}, 404)
        return _json_response({"matches": matches})


class SpamReviewTask(Resource):
    @log_response
    @verify_spam_detection_read_permissions
    @login_required
    def get(self):
        statuses = request.args.getlist("status") or None
        try:
            limit = _bounded_limit(request.args.get("limit"), 100, 500)
            return _json_response({"records": store.list_review(current_app.config, statuses, limit=limit)})
        except ValueError as exc:
            return _json_response({"message": str(exc)}, 400)


class SpamReviewManualInspectTask(Resource):
    @log_response
    @verify_spam_detection_read_permissions
    @login_required
    def post(self):
        payload = _body()
        try:
            return _json_response(
                {
                    "repository": remediation.inspect_false_negative(
                        current_app.config,
                        payload.get("namespace"),
                        payload.get("repository"),
                    )
                }
            )
        except remediation.RemediationError as exc:
            return _json_response({"message": str(exc)}, 400)


class SpamReviewManualTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self):
        payload = _body()
        try:
            record = remediation.add_false_negative(
                current_app.config,
                payload.get("namespace"),
                payload.get("repository"),
                reason=payload.get("reason"),
                operator=_operator(),
            )
            return _json_response({"record": record}, 201)
        except remediation.RemediationError as exc:
            return _json_response({"message": str(exc)}, 400)


class SpamAuditTask(Resource):
    @log_response
    @verify_spam_detection_read_permissions
    @login_required
    def get(self):
        try:
            limit = _bounded_limit(request.args.get("limit"), 100, 500)
            return _json_response(
                {"actions": store.list_audit_actions(current_app.config, limit=limit)}
            )
        except ValueError as exc:
            return _json_response({"message": str(exc)}, 400)


class SpamReviewQuarantineTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, record_uuid):
        try:
            return _json_response({"record": remediation.quarantine(current_app.config, record_uuid, _operator())})
        except remediation.RemediationError as exc:
            return _json_response({"message": str(exc)}, 400)


class SpamReviewRestoreTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, record_uuid):
        try:
            return _json_response({"record": remediation.restore(current_app.config, record_uuid, _operator())})
        except remediation.RemediationError as exc:
            return _json_response({"message": str(exc)}, 400)


class SpamReviewReopenTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, record_uuid):
        try:
            return _json_response(
                {
                    "record": remediation.reopen(
                        current_app.config,
                        record_uuid,
                        reason=_body().get("reason"),
                        operator=_operator(),
                    )
                }
            )
        except remediation.RemediationError as exc:
            return _json_response({"message": str(exc)}, 400)


class SpamReviewDismissTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, record_uuid):
        try:
            return _json_response({"record": remediation.dismiss(current_app.config, record_uuid, _operator())})
        except remediation.RemediationError as exc:
            return _json_response({"message": str(exc)}, 400)


class SpamReviewClassifyTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, record_uuid):
        try:
            return _json_response(
                {
                    "record": remediation.classify(
                        current_app.config,
                        record_uuid,
                        _body().get("label"),
                        _operator(),
                    )
                }
            )
        except remediation.RemediationError as exc:
            return _json_response({"message": str(exc)}, 400)


class SpamReviewRedactTask(Resource):
    @log_response
    @verify_spam_detection_write_permissions
    @login_required
    def post(self, record_uuid):
        try:
            return _json_response(
                {
                    "record": remediation.redact(
                        current_app.config,
                        record_uuid,
                        redacted_description=_body().get("redacted_description"),
                        operator=_operator(),
                    )
                }
            )
        except remediation.RemediationError as exc:
            return _json_response({"message": str(exc)}, 400)
