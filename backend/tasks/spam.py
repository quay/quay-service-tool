from flask_restful import Resource, reqparse
from flask_login import login_required
from flask import make_response, request
import json
import logging

from utils import log_response, verify_admin_permissions
from data.model import spam, db_transaction

logger = logging.getLogger(__name__)


class SpamRuleListTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def get(self):
        try:
            rules = spam.get_spam_detection_rules()
            return make_response(
                json.dumps({"rules": [r.get_view() for r in rules]}), 200
            )
        except Exception as e:
            logger.exception("Failed to list spam detection rules")
            return make_response(
                json.dumps({"message": "Failed to list rules"}), 500
            )

    @log_response
    @verify_admin_permissions
    @login_required
    def post(self):
        try:
            data = request.get_json()
            if not data or "name" not in data or "rule_type" not in data:
                return make_response(
                    json.dumps({"message": "name and rule_type are required"}), 400
                )
            rule = spam.create_spam_detection_rule(
                name=data["name"],
                rule_type=data["rule_type"],
                pattern=data.get("pattern"),
                config=data.get("config"),
                confidence_score=data.get("confidence_score", 50),
            )
            return make_response(json.dumps(rule.get_view()), 201)
        except spam.InvalidSpamDetectionRule as e:
            return make_response(json.dumps({"message": str(e)}), 400)
        except Exception as e:
            logger.exception("Failed to create spam detection rule")
            return make_response(
                json.dumps({"message": "Failed to create rule"}), 500
            )


class SpamRuleDetailTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def get(self, rule_uuid):
        try:
            rule = spam.get_spam_detection_rule_by_uuid(rule_uuid)
            if not rule:
                return make_response(
                    json.dumps({"message": "Rule not found"}), 404
                )
            return make_response(json.dumps(rule.get_view()), 200)
        except Exception as e:
            logger.exception("Failed to get spam detection rule")
            return make_response(
                json.dumps({"message": "Failed to get rule"}), 500
            )

    @log_response
    @verify_admin_permissions
    @login_required
    def put(self, rule_uuid):
        try:
            data = request.get_json()
            if not data:
                return make_response(
                    json.dumps({"message": "Request body is required"}), 400
                )
            spam.update_spam_detection_rule(rule_uuid, **data)
            rule = spam.get_spam_detection_rule_by_uuid(rule_uuid)
            return make_response(json.dumps(rule.get_view()), 200)
        except spam.SpamDetectionRuleNotFound:
            return make_response(
                json.dumps({"message": "Rule not found"}), 404
            )
        except spam.InvalidSpamDetectionRule as e:
            return make_response(json.dumps({"message": str(e)}), 400)
        except Exception as e:
            logger.exception("Failed to update spam detection rule")
            return make_response(
                json.dumps({"message": "Failed to update rule"}), 500
            )

    @log_response
    @verify_admin_permissions
    @login_required
    def delete(self, rule_uuid):
        try:
            spam.delete_spam_detection_rule(rule_uuid)
            return make_response(json.dumps({"message": "Rule deleted"}), 200)
        except spam.SpamDetectionRuleNotFound:
            return make_response(
                json.dumps({"message": "Rule not found"}), 404
            )
        except Exception as e:
            logger.exception("Failed to delete spam detection rule")
            return make_response(
                json.dumps({"message": "Failed to delete rule"}), 500
            )


class FlaggedRepoListTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def get(self):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("status", type=str, location="args")
            parser.add_argument("min_confidence", type=int, default=0, location="args")
            parser.add_argument("namespace", type=str, location="args")
            parser.add_argument("scan_id", type=str, location="args")
            parser.add_argument("page_token", type=str, location="args")
            parser.add_argument("limit", type=int, default=50, location="args")
            args = parser.parse_args()

            repos, next_token = spam.get_quarantined_repos(
                status=args.get("status"),
                min_confidence=args.get("min_confidence", 0),
                namespace=args.get("namespace"),
                scan_id=args.get("scan_id"),
                page_token=args.get("page_token"),
                limit=min(args.get("limit", 50), 100),
            )
            result = {"flagged_repos": [r.get_view() for r in repos]}
            if next_token:
                result["next_page_token"] = next_token
            return make_response(json.dumps(result), 200)
        except Exception as e:
            logger.exception("Failed to list flagged repos")
            return make_response(
                json.dumps({"message": "Failed to list flagged repos"}), 500
            )


class FlaggedRepoDetailTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def get(self, repo_uuid):
        try:
            repo = spam.get_quarantined_repo_by_uuid(repo_uuid)
            if not repo:
                return make_response(
                    json.dumps({"message": "Flagged repo not found"}), 404
                )
            return make_response(json.dumps(repo.get_view()), 200)
        except Exception as e:
            logger.exception("Failed to get flagged repo")
            return make_response(
                json.dumps({"message": "Failed to get flagged repo"}), 500
            )


class QuarantineRepoTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def post(self, repo_uuid):
        try:
            from flask_login import current_user
            actioned_by = getattr(current_user, "username", "admin")
            spam.quarantine_repository(repo_uuid, actioned_by)
            return make_response(json.dumps({"status": "quarantined"}), 200)
        except spam.QuarantinedRepoNotFound:
            return make_response(
                json.dumps({"message": "Flagged repo not found"}), 404
            )
        except Exception as e:
            logger.exception("Failed to quarantine repo")
            return make_response(
                json.dumps({"message": "Failed to quarantine repo"}), 500
            )


class RestoreRepoTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def post(self, repo_uuid):
        try:
            from flask_login import current_user
            actioned_by = getattr(current_user, "username", "admin")
            spam.restore_repository(repo_uuid, actioned_by)
            return make_response(json.dumps({"status": "restored"}), 200)
        except spam.QuarantinedRepoNotFound:
            return make_response(
                json.dumps({"message": "Flagged repo not found"}), 404
            )
        except Exception as e:
            logger.exception("Failed to restore repo")
            return make_response(
                json.dumps({"message": "Failed to restore repo"}), 500
            )


class DismissRepoTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def post(self, repo_uuid):
        try:
            from flask_login import current_user
            actioned_by = getattr(current_user, "username", "admin")
            spam.dismiss_quarantined_repo(repo_uuid, actioned_by)
            return make_response(json.dumps({"status": "dismissed"}), 200)
        except spam.QuarantinedRepoNotFound:
            return make_response(
                json.dumps({"message": "Flagged repo not found"}), 404
            )
        except Exception as e:
            logger.exception("Failed to dismiss repo")
            return make_response(
                json.dumps({"message": "Failed to dismiss repo"}), 500
            )
