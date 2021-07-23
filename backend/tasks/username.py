from flask import request
from flask_restful import Resource
from flask import make_response
from flask_restful import reqparse
import re
import logging
logger = logging.getLogger(__name__)

class UsernameTask(Resource):    
    def put(self):
        parser = reqparse.RequestParser()
        parser.add_argument('newUsername', type=str, help='new username')
        parser.add_argument('currentUsername', type=str, help='current username')
        args = parser.parse_args()
        new_user_name = args.get("newUsername")
        current_user_name = args.get("currentUsername")
        
        if not re.match('^[a-zA-Z][a-zA-Z0-9]*$', new_user_name):
            return make_response(('Usernames should only contain alphanumerical characters and only starts with a letter'), 400)
        
        try:
            with request.db.cursor() as cur:
                if new_user_name and current_user_name:
                    cur.execute('SELECT * FROM user WHERE username=%s',(current_user_name,))
                    if cur.rowcount == 0:
                        return make_response(('Could not find user ' + current_user_name), 404)
                    
                    cur.execute('SELECT * FROM user WHERE username=%s',(new_user_name,))
                    if cur.rowcount != 0:
                        return make_response('Username already exists', 409)
                    else:
                        cur.execute('Update user SET username = %s WHERE username = %s', (new_user_name, current_user_name))
                        request.db.commit()
                        return make_response(('Username has been updated to ' + new_user_name), 200)
        except Exception as e:
            logger.exception("Unable to update the username: " + str(e))
