from flask_login import login_required
from flask_restful import Resource
from flask import make_response
import json

from utils import log_response, verify_export_compliance_permissions
from data.model import user


class FederatedUserTask(Resource):

    @log_response
    @verify_export_compliance_permissions
    @login_required
    def get(self, username):
        if username is None:
            return make_response(
                json.dumps({"message": "`username` is required"}), 400
            )
        try:
            found_user = user.get_quay_user_from_federated_login_name(username)
            if found_user is None:
                return make_response(
                    json.dumps({"message": f"Could not find user with username `{username}`"}), 404
                )
            private_repo_count = user.get_private_repo_count(found_user.username)
            public_repo_count = user.get_public_repo_count(found_user.username)

            return make_response(
                json.dumps({
                    "username": found_user.username,
                    "enabled": found_user.enabled,
                    "paid_user": True if found_user.stripe_id else False,
                    "last_accessed": str(found_user.last_accessed),
                    "is_organization": found_user.organization,
                    "company": found_user.company,
                    "creation_date": str(found_user.creation_date),
                    "last_accessed": str(found_user.last_accessed),
                    "invoice_email": found_user.invoice_email,
                    "private_repo_count": private_repo_count,
                    "public_repo_count": public_repo_count,
                }),
                200,
            )
        # Same output for Quay username/email search.
        except Exception:
            return make_response(
                json.dumps({"message": "Unable to fetch user"}), 500
            )
