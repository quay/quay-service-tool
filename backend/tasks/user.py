from flask_restful import Resource, reqparse, inputs
from flask import request
from psycopg2.extras import RealDictCursor
from pymysql.cursors import DictCursor
import os
from flask import make_response
import json
import logging
from flask_login import login_required
logger = logging.getLogger(__name__)


class UserTask(Resource):

    def __init__(self):
        # user is a reserved word in postgres, need to include quotes
        self.USER_TABLE_NAME = "\"user\"" if os.environ.get('IS_LOCAL') else "`user`"

    @login_required
    def get(self, user):
        if user is None or len(user) == 0:
            return make_response(json.dumps({'message': 'Parameter \'user\' is required'}), 400)

        try:
            with request.db.cursor(cursor_factory=RealDictCursor) if os.environ.get('IS_LOCAL') else request.db.cursor(DictCursor) as cur:
                cur.execute(f"""SELECT username, enabled FROM {self.USER_TABLE_NAME} WHERE username=%s""", (user,))
                result = cur.fetchone()
                if result is None:
                    return make_response(json.dumps({'message': f"Could not find user {user}"}), 404)
                return make_response(json.dumps(result), 200)
        except Exception as e:
            logger.exception("Unable to fetch users: " + str(e))
            return make_response(json.dumps({'message': f"Unable to fetch user {user}"}), 500)

    # Used for enabling a user, under the general put function
    # Trying to keep this as RESTful as possible, but may want to separate out into it's own 'enable' endpoint
    @login_required
    def put(self, user):
        # Define params
        parser = reqparse.RequestParser()
        parser.add_argument('enable', type=inputs.boolean, location='args')
        args = parser.parse_args()
        enable = args.get('enable')

        # Check params
        if enable is None or user is None:
            return make_response(json.dumps({'message': 'Parameter \'enable\' required'}), 400)

        try:
            with request.db.cursor(cursor_factory=RealDictCursor) if os.environ.get('IS_LOCAL') else request.db.cursor(DictCursor) as cur:

                # Make sure user exists and can be enabled/disabled
                cur.execute(f"""SELECT username, enabled, id FROM {self.USER_TABLE_NAME} WHERE username=%s""", (user,))
                result = cur.fetchone()
                if result is None:
                    return make_response(json.dumps({'message': f"Could not find user {user}"}), 404)
                if result["enabled"] and enable:
                    return make_response(json.dumps({'message': f"User {user} already enabled"}), 400)
                if not result["enabled"] and not enable:
                    return make_response(json.dumps({'message': f"User {user} already disabled"}), 400)

                # Update User
                cur.execute(f"""UPDATE {self.USER_TABLE_NAME} SET enabled=%s WHERE username=%s""", (enable, user))

                # If user is being disabled clean up the builds, build triggers, mirrors, and build queue
                if not enable:
                    user_id = result["id"]
                    cur.execute("SELECT id FROM repository WHERE namespace_user_id=%s", (user_id,))
                    repositories = cur.fetchall()
                    if len(repositories) > 0:
                        # Convert list of rows into list of repo id's as strings, then join
                        repo_ids = ", ".join([str(repo["id"]) for repo in repositories])
                        cur.execute(f"DELETE FROM repositorybuild WHERE repository_id IN ({repo_ids})")
                        cur.execute(f"DELETE FROM repositorybuildtrigger WHERE repository_id IN ({repo_ids})")
                        cur.execute(f"DELETE FROM repomirrorconfig WHERE repository_id IN ({repo_ids})")
                        queue_prefix = "dockerfilebuild/%s/%%" % user
                        cur.execute("DELETE FROM queueitem WHERE queue_name LIKE %s", (queue_prefix,))

            request.db.commit()
            return make_response(json.dumps({'message': 'User updated successfully', 'user': user, 'enabled': enable}), 200)
        except Exception as e:
            logger.exception("Unable to update enable status: " + str(e))
            return make_response(json.dumps({'message': 'Unable to update enable status'}), 500)
