from flask import request
from flask_restful import Resource
from flask import make_response
from flask_restful import reqparse
import traceback

class UsernameTask(Resource):    
    def put(self):
        parser = reqparse.RequestParser()
        parser.add_argument('newUsername', type=str, help='new username')
        parser.add_argument('currentUsername', type=str, help='current username')
        args = parser.parse_args()
        new_user_name = args.get("newUsername")
        current_user_name = args.get("currentUsername")
        
        try:
            with request.db.cursor() as cur:
                if new_user_name and current_user_name:
                    cur.execute('SELECT * FROM public."user" WHERE username=%s',(new_user_name,))
                    duplicatedNames = cur.rowcount
                    cur.execute('SELECT * FROM public."user" WHERE username=%s',(current_user_name,))
                    if duplicatedNames != 0:
                        return make_response('existed username', 409)
                    elif cur.rowcount == 0:
                        return make_response(('could not find user ' + current_user_name), 404)
                    else:
                        cur.execute('Update public."user" SET username = %s WHERE username = %s', (new_user_name, current_user_name))
                        request.db.commit()
                        return make_response(('username is updated to ' + new_user_name), 200)
        except Exception as e:
            traceback.print_exc() 
