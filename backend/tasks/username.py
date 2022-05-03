from flask_restful import Resource
from flask_login import login_required
from flask import make_response
from flask_restful import reqparse
from data import model
from data.model import InvalidUsernameException, user
from utils import AppLogger
import json


class UsernameTask(Resource):
    @login_required
    def put(self):
        parser = reqparse.RequestParser()
        parser.add_argument("newUsername", type=str, help="new username")
        parser.add_argument("currentUsername", type=str, help="current username")
        args = parser.parse_args()
        new_user_name = args.get("newUsername")
        current_user_name = args.get("currentUsername")

        try:
            curr_user = user.get_namespace_user(current_user_name)
            if curr_user is None:
                response = f"Could not find user {current_user_name}"
                AppLogger.log_error(args=json.dumps(args), response=response)
                return make_response(json.dumps({"message": response}), 404)
            new_username_check = user.get_namespace_user(new_user_name)
            if new_username_check is not None:
                response = "Username already exists"
                AppLogger.log_error(args=json.dumps(args), response=response)
                return make_response(json.dumps({"message": response}), 409)
            user.change_username(curr_user.id, new_user_name)
            response = f"Username has been updated to {new_user_name}"
            AppLogger.log_info(args=json.dump(args), response=response)
            return make_response(response, 200)
        except InvalidUsernameException:
            response = "Usernames should only contain alphanumerical characters and only starts with a letter"
            AppLogger.log_error(args=json.dumps(args), response=response)
            return make_response(
                json.dumps({"message": response}),
                400,
            )
        except Exception as e:
            AppLogger.log_exception(
                args=json.dumps(args),
                response=f"Unable to update the username: {str(e)}",
            )
            return make_response(
                json.dumps({"message": "Unable to update the username"}), 500
            )
