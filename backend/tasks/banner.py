from flask import request
from flask_login import login_required
from flask_restful import Resource
from flask import make_response
from flask_restful import reqparse
from psycopg2.extras import RealDictCursor
from pymysql.cursors import DictCursor
from utils import is_valid_severity
import json
import os
import logging
logger = logging.getLogger(__name__)


class BannerTask(Resource):

    @login_required
    def get(self):
        try:
            with request.db.cursor(cursor_factory=RealDictCursor) if os.environ.get('IS_LOCAL') else request.db.cursor(DictCursor) as cur:
                cur.execute("SELECT * from messages")
                result = cur.fetchall()
                request.db.commit()
                return make_response(json.dumps(result), 200)  
        except Exception as e:
            logger.exception("Unable to fetch banners: " + str(e))
            return make_response(json.dumps({'message': 'Unable to fetch banners'}), 500)

    @login_required
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('message', type=str, help='banner message')
        parser.add_argument('severity', type=str, help='severity')
        args = parser.parse_args()
        message = args.get("message")
        severity = args.get("severity")

        if not is_valid_severity(severity):
            return make_response(json.dumps({'message': 'Invalid severity value'}), 400)

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
            logger.exception("Unable to create a new banner: " + str(e))
            return make_response(json.dumps({'message': 'Unable to create a new banner'}), 500)

    @login_required
    def put(self):
        parser = reqparse.RequestParser()
        parser.add_argument('message', type=str, help='banner message')
        parser.add_argument('severity', type=str, help='severity')
        parser.add_argument('id', type=str, help='banner id')
        args = parser.parse_args()
        message = args.get("message")
        severity = args.get("severity")
        id = args.get("id")
        
        if not is_valid_severity(severity):
            return make_response(json.dumps({'message': 'Invalid severity value'}), 400)
        
        try:
            with request.db.cursor() as cur:
                if message and severity:
                    cur.execute('UPDATE messages SET content = %s, severity = %s WHERE id = %s', (message, severity, id))
                    request.db.commit()
                    return make_response(('updated'), 200)
        except Exception as e:
            logger.exception("Unable to update the banner: " + str(e))
            return make_response(json.dumps({'message': 'Unable to update the banner'}), 500)

    @login_required
    def delete(self, id):
        try:
            with request.db.cursor() as cur:
                cur.execute('DELETE FROM messages WHERE id = %s', (id,))
                request.db.commit()
                return make_response(('deleted'), 200)
        except Exception as e:
            logger.exception("Unable to delete the banner: " + str(e))
            return make_response(json.dumps({'message': 'Unable to delete the banner'}), 500)


