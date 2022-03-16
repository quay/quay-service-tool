from flask import request
from flask_restful import Resource
from flask_login import login_required
from flask import make_response
from flask_restful import reqparse
from data import model
from data.model import (InvalidUsernameException, user)
import json
import re
import logging
logger = logging.getLogger(__name__)


class UsernameTask(Resource):

    @login_required
    def put(self):
        parser = reqparse.RequestParser()
        parser.add_argument('newUsername', type=str, help='new username')
        parser.add_argument('currentUsername', type=str, help='current username')
        args = parser.parse_args()
        new_user_name = args.get("newUsername")
        current_user_name = args.get("currentUsername")
        
        try:
            curr_user = user.get_namespace_user(current_user_name)
            if curr_user is None:
                return make_response(json.dumps({'message': f"Could not find user {current_user_name}"}), 404)
            new_username_check = user.get_namespace_user(new_user_name) 
            if new_username_check is not None:
                return make_response(json.dumps({'message': 'Username already exists'}), 409)
            user.change_username(curr_user.id, new_user_name)
            return make_response(('Username has been updated to ' + new_user_name), 200)
        except InvalidUsernameException:
            return make_response(json.dumps({'message': 'Usernames should only contain alphanumerical characters and only starts with a letter'}), 400)
        except Exception as e:
            logger.exception("Unable to update the username: " + str(e))
