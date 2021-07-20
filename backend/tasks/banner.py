from flask import request
from flask_restful import Resource
from flask import make_response, jsonify
from flask_restful import reqparse
from psycopg2.extras import RealDictCursor
from pymysql.cursors import DictCursor
import traceback
import json
import os

class BannerTask(Resource):
    def get(self):
        try:
            cur = request.db.cursor(cursor_factory=RealDictCursor) if os.environ.get('IS_LOCAL') else request.db.cursor(DictCursor)
            cur.execute("SELECT * from messages")
            result = cur.fetchall()
            request.db.commit()
            return make_response(json.dumps(result), 200)  
        except Exception as e:
            traceback.print_exc()
            return make_response(('Unable to fetch banners'), 500)
    
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('message', type=str, help='banner message')
        parser.add_argument('severity', type=str, help='severity')
        args = parser.parse_args()
        message = args.get("message")
        severity = args.get("severity")
        try:
            with request.db.cursor() as cur:
                if message and severity:
                    cur.execute("SELECT id from mediatype WHERE name='text/markdown'")
                    result = cur.fetchone()
                    media_type_id = int(result[0])
                    cur.execute('INSERT INTO messages (content, media_type_id, severity) VALUES (%s, %s, %s)', (message, media_type_id, severity))
                    request.db.commit()
                    return make_response(('created'), 200)
        except Exception as e:
            traceback.print_exc()
            return make_response(('Unable to create a new banner'), 500)
    
    def put(self):
        parser = reqparse.RequestParser()
        parser.add_argument('message', type=str, help='banner message')
        parser.add_argument('severity', type=str, help='severity')
        parser.add_argument('id', type=str, help='banner id')
        args = parser.parse_args()
        message = args.get("message")
        severity = args.get("severity")
        id = args.get("id")
        try:
            with request.db.cursor() as cur:
                if message and severity:
                    cur.execute('UPDATE messages SET content = %s, severity = %s WHERE id = %s', (message, severity, id))
                    request.db.commit()
                    return make_response(('updated'), 200)
        except Exception as e:
            traceback.print_exc()
            return make_response(('Unable to update the banner'), 500)
        
    def delete(self, id):
        try:
            with request.db.cursor() as cur:
                cur.execute('DELETE FROM messages WHERE id = %s', (id,))
                request.db.commit()
                return make_response(('deleted'), 200)
        except Exception as e:
            traceback.print_exc()
            return make_response(('Unable to delete the banner'), 500)


