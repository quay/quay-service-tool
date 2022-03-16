from flask_restful import Resource, reqparse, inputs
from flask import request
from psycopg2.extras import RealDictCursor
from pymysql.cursors import DictCursor
import os
from flask import make_response
import json
import logging
from flask_login import login_required
from data.model import user, db_transaction
from data.database import (
    Repository,
    RepositoryBuild,
    RepositoryBuildTrigger,
    RepoMirrorConfig,
)
from data.queue import WorkQueue
from utils import create_transaction as tf

logger = logging.getLogger(__name__)


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
secscan_notification_queue = WorkQueue(SECSCAN_V4_NOTIFICATION_QUEUE_NAME, tf, has_namespace=False)
export_action_logs_queue = WorkQueue(EXPORT_ACTION_LOGS_QUEUE_NAME, tf, has_namespace=True)
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
    @login_required
    def get(self, username):
        if username is None or len(username) == 0:
            return make_response(json.dumps({"message": "Parameter 'user' is required"}), 400)
        try:
            found_user = user.get_namespace_user(username)
            if found_user is None:
                return make_response(
                    json.dumps({"message": f"Could not find user {username}"}), 404
                )
            return make_response(
                json.dumps({"username": found_user.username, "enabled": found_user.enabled}), 200
            )
        except Exception as e:
            logger.exception("Unable to fetch users: " + str(e))
            return make_response(json.dumps({"message": f"Unable to fetch user {username}"}), 500)

    # Used for enabling a user, under the general put function
    # Trying to keep this as RESTful as possible, but may want to separate out into it's own 'enable' endpoint
    @login_required
    def put(self, username):
        # Define params
        parser = reqparse.RequestParser()
        parser.add_argument("enable", type=inputs.boolean, location="args")
        args = parser.parse_args()
        enable = args.get("enable")

        # Check params
        if enable is None or username is None:
            return make_response(json.dumps({"message": "Parameter 'enable' required"}), 400)

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
                repositories_query = Repository.select().where(
                    Repository.namespace_user == found_user
                )
                if len(repositories_query.clone()):
                    builds = list(
                        RepositoryBuild.select().where(
                            RepositoryBuild.repository << list(repositories_query)
                        )
                    )

                    triggers = list(
                        RepositoryBuildTrigger.select().where(
                            RepositoryBuildTrigger.repository << list(repositories_query)
                        )
                    )

                    mirrors = list(
                        RepoMirrorConfig.select().where(
                            RepoMirrorConfig.repository << list(repositories_query)
                        )
                    )

                    # Delete all builds for the user's repositories.
                    if builds:
                        RepositoryBuild.delete().where(RepositoryBuild.id << builds).execute()

                    # Delete all build triggers for the user's repositories.
                    if triggers:
                        RepositoryBuildTrigger.delete().where(
                            RepositoryBuildTrigger.id << triggers
                        ).execute()

                    # Delete all mirrors for the user's repositories.
                    if mirrors:
                        RepoMirrorConfig.delete().where(RepoMirrorConfig.id << mirrors).execute()

                    # Delete all queue items for the user's namespace.
                    dockerfile_build_queue.delete_namespaced_items(found_user.username)
        except Exception as e:
            logger.exception("Unable to update enable status: " + str(e))
            return make_response(json.dumps({"message": "Unable to update enable status"}), 500)

        return make_response(
            json.dumps(
                {"message": "User updated successfully", "user": username, "enabled": enable}
            ),
            200,
        )

    @login_required
    def delete(self, username):
        found_user = user.get_namespace_user(username)
        if found_user is None:
            return make_response(json.dumps({"message": f"Could not find user {username}"}), 404)

        user.mark_namespace_for_deletion(found_user, all_queues, namespace_gc_queue, force=True)
        return "", 204
