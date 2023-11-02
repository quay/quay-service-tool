from flask_restful import Resource, reqparse, inputs
from flask_login import login_required
from flask import make_response
import json

from utils import create_transaction as tf, log_response, verify_admin_permissions, verify_export_compliance_permissions, verify_admin_or_export_perm
from data.model import user, db_transaction
from data.database import (
    Repository,
    RepositoryBuild,
    RepositoryBuildTrigger,
    RepoMirrorConfig,
)
from data.queue import WorkQueue

NOTIFICATION_QUEUE_NAME = "notification"
DOCKERFILE_BUILD_QUEUE_NAME = "dockerfilebuild"
REPLICATION_QUEUE_NAME = "imagestoragereplication"
CHUNK_CLEANUP_QUEUE_NAME = "chunk_cleanup"
NAMESPACE_GC_QUEUE_NAME = "namespacegc"
REPOSITORY_GC_QUEUE_NAME = "repositorygc"
EXPORT_ACTION_LOGS_QUEUE_NAME = "exportactionlogs"
SECSCAN_V4_NOTIFICATION_QUEUE_NAME = "secscanv4"


image_replication_queue = WorkQueue(REPLICATION_QUEUE_NAME, tf, has_namespace=False)
dockerfile_build_queue = WorkQueue(DOCKERFILE_BUILD_QUEUE_NAME, tf, has_namespace=True)
notification_queue = WorkQueue(NOTIFICATION_QUEUE_NAME, tf, has_namespace=True)
secscan_notification_queue = WorkQueue(
    SECSCAN_V4_NOTIFICATION_QUEUE_NAME, tf, has_namespace=False
)
export_action_logs_queue = WorkQueue(
    EXPORT_ACTION_LOGS_QUEUE_NAME, tf, has_namespace=True
)
repository_gc_queue = WorkQueue(REPOSITORY_GC_QUEUE_NAME, tf, has_namespace=True)
namespace_gc_queue = WorkQueue(NAMESPACE_GC_QUEUE_NAME, tf, has_namespace=False)
chunk_cleanup_queue = WorkQueue(CHUNK_CLEANUP_QUEUE_NAME, tf)


all_queues = [
    image_replication_queue,
    dockerfile_build_queue,
    notification_queue,
    chunk_cleanup_queue,
    repository_gc_queue,
    namespace_gc_queue,
]


class UserTask(Resource):
    @log_response
    @verify_admin_or_export_perm
    @login_required
    def get(self, username):
        if username is None or len(username) == 0:
            return make_response(
                json.dumps({"message": "Parameter 'user' is required"}), 400
            )
        try:
            found_user = user.get_namespace_user(username)
            if found_user is None:
                return make_response(
                    json.dumps({"message": f"Could not find user {username}"}), 404
                )

            return make_response(
                json.dumps(
                    {"username": found_user.username, "enabled": found_user.enabled}
                ),
                200,
            )
        except Exception as e:
            return make_response(
                json.dumps({"message": f"Unable to fetch user {username}"}), 500
            )

    # Used for enabling a user, under the general put function
    # Trying to keep this as RESTful as possible, but may want to separate out into it's own 'enable' endpoint
    @log_response
    @verify_admin_or_export_perm
    @login_required
    def put(self, username):
        # Define params
        parser = reqparse.RequestParser()
        parser.add_argument("enable", type=inputs.boolean, location="args")
        args = parser.parse_args()
        enable = args.get("enable")

        # Check params
        if enable is None or username is None:
            return make_response(
                json.dumps({"message": "Parameter 'enable' required"}), 400
            )

        try:
            found_user = user.get_namespace_user(username)
            if found_user is None:
                return make_response(
                    json.dumps({"message": f"Could not find user {username}"}), 404
                )
            if found_user.enabled and enable:
                return make_response(
                    json.dumps({"message": f"User {username} already enabled"}), 400
                )
            if not found_user.enabled and not enable:
                return make_response(
                    json.dumps({"message": f"User {username} already disabled"}), 400
                )
            with db_transaction():
                found_user.enabled = enable
                found_user.save()
                
        except Exception as e:
            return make_response(
                json.dumps({"message": "Unable to update enable status"}), 500
            )

        return make_response(
            json.dumps(
                {
                    "message": "User updated successfully",
                    "user": username,
                    "enabled": enable,
                }
            ),
            200,
        )

    @log_response
    @verify_admin_permissions
    @login_required
    def delete(self, username):
        found_user = user.get_namespace_user(username)
        if found_user is None:
            return make_response(
                json.dumps({"message": f"Could not find user {username}"}), 404
            )

        user.mark_namespace_for_deletion(
            found_user, all_queues, namespace_gc_queue, force=True
        )
        return make_response(
            json.dumps({"message": "User deleted successfully", "user": username}), 200
        )


class FetchUserFromNameTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def get(self, quayusername):
        if quayusername is None:
            return make_response(
                json.dumps({"message": "Parameter 'quay username' is required"}), 400
            )
        try:
            found_user = user.get_namespace_user(quayusername)
            if found_user is None:
                return make_response(
                    json.dumps({"message": f"Could not find user {quayusername}"}), 404
                )

            private_repo_count = user.get_private_repo_count(found_user.username)
            public_repo_count = user.get_public_repo_count(found_user.username)

            return make_response(
                json.dumps({
                    "email": found_user.email,
                    "enabled": found_user.enabled,
                    "paid_user": True if found_user.stripe_id else False,
                    "last_accessed": str(found_user.last_accessed),
                    "is_organization": found_user.organization,
                    "company": found_user.company,
                    "creation_date": str(found_user.creation_date),
                    "invoice_email": found_user.invoice_email_address,
                    "stripe_id": found_user.stripe_id,
                    "private_repo_count": private_repo_count,
                    "public_repo_count": public_repo_count,
                }),
                200,
            )
        except Exception as e:
            return make_response(
                json.dumps({"message": f"Unable to fetch user {quayusername}"}), 500
            )


class FetchUserFromEmailTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def get(self, quayuseremail):
        if quayuseremail is None:
            return make_response(
                json.dumps({"message": "Parameter 'quay useremail' is required"}), 400
            )
        try:
            found_user = user.find_user_by_email(quayuseremail)
            if found_user is None:
                return make_response(
                    json.dumps({"message": f"Could not find user {quayuseremail}"}), 404
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
                    "invoice_email": found_user.invoice_email_address,
                    "stripe_id": found_user.stripe_id,                    
                    "private_repo_count": private_repo_count,
                    "public_repo_count": public_repo_count,
                }),
                200,
            )
        except Exception as e:
            return make_response(
                json.dumps({"message": f"Unable to fetch user {quayuseremail}"}), 500
            )


class FetchUserFromStripeID(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def get(self, stripe_id):
        if stripe_id is None:
            return make_response(
                json.dumps({"message": "Parameter 'quay stripe id' is required"}), 400
            )
        try:
            found_user = user.get_user_or_org_by_customer_id(stripe_id)
            if found_user is None:
                return make_response(
                    json.dumps({"message": f"Could not find user with stripe ID {stripe_id}"}), 404
                )
            private_repo_count = user.get_private_repo_count(found_user.username)
            public_repo_count = user.get_public_repo_count(found_user.username)

            return make_response(
                json.dumps({
                    "username": found_user.username,
                    "enabled": found_user.enabled,
                    "paid_user": True if found_user.stripe_id else False,
                    "is_organization": found_user.organization,
                    "company": found_user.company,
                    "creation_date": str(found_user.creation_date),
                    "last_accessed": str(found_user.last_accessed),
                    "invoice_email": found_user.invoice_email_address,
                    "stripe_id": found_user.stripe_id,
                    "private_repo_count": private_repo_count,
                    "public_repo_count": public_repo_count,
                }),
                200,
            )
        except Exception as e:
            return make_response(
                json.dumps({"message": f"Unable to fetch user with stripe ID {stripe_id}"}), 500
            )

class UpdateEmailTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def put(self):
        parser = reqparse.RequestParser()
        parser.add_argument("username", type=str, help="current username")
        parser.add_argument("newEmail", type=str, help="new email")
        args = parser.parse_args()
        username = args.get("username")
        new_email = args.get("newEmail")

        try:
            curr_user = user.get_namespace_user(username)
            if curr_user is None:
                return make_response(
                    json.dumps({"message": f"Could not find user {username}"}),
                    404,
                )
            user.update_email(curr_user, new_email, True)
            return make_response(f"email for user {username} has been updated to {new_email}", 200)
        except DataModelException as e:
            return make_response(
                json.dumps(
                    {
                        "message": str(e)
                    }
                ),
                400,
            )
        except Exception as e:
            return make_response(
                json.dumps({"message": "Unable to update the username" + str(e)}), 500
            )
