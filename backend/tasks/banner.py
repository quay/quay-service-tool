from flask import request
from flask_login import login_required
from flask_restful import Resource
from flask import make_response
from flask_restful import reqparse
from psycopg2.extras import RealDictCursor
from pymysql.cursors import DictCursor
from playhouse.shortcuts import model_to_dict
from utils import is_valid_severity
import json
import os
import logging
from data.model import (message, db_transaction)
from data.database import Messages

logger = logging.getLogger(__name__)


class BannerTask(Resource):

    @login_required
    def get(self):
        try:
            messages = { "messages": [ model_to_dict(m) for m in message.get_messages() ] }
            return make_response(json.dumps(messages), 200)  
        except Exception as e:
            logger.exception("Unable to fetch banners: " + str(e))
            return make_response(json.dumps({'message': 'Unable to fetch banners'}), 500)

    @login_required
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('message', type=str, help='banner message')
        parser.add_argument('severity', type=str, help='severity')
        args = parser.parse_args()
        content = args.get("message")
        severity = args.get("severity")

        if not is_valid_severity(severity):
            return make_response(json.dumps({'message': 'Invalid severity value'}), 400)

        try:
            with db_transaction():
                message.create([{'content': content, 'severity': severity, "media_type": "text/markdown"}])
            return make_response(json.dumps({'message': 'Banner created'}), 201)
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
        content = args.get("message")
        severity = args.get("severity")
        id = args.get("id")
        
        if not is_valid_severity(severity):
            return make_response(json.dumps({'message': 'Invalid severity value'}), 400)
        if content == "" or severity == "":
            return make_response(json.dumps({'message': 'Fields severity and message required'}), 400)
        
        try:
            with db_transaction():
                Messages.update({'content': content, 'severity': severity}).where(Messages.id == id).execute()
            return make_response(('updated'), 200)
        except Exception as e:
            logger.exception("Unable to update the banner: " + str(e))
            return make_response(json.dumps({'message': 'Unable to update the banner'}), 500)

    @login_required
    def delete(self, id):
        try:
            Messages.get(Messages.id == id)
        except Messages.DoesNotExist:
            return make_response(('Banner not found'), 404) 
        except Exception as e:
            logger.exception("Unable to check banner existence: " + str(e))
            return make_response(json.dumps({'message': 'Unable to check banner existence'}), 500)

        try:
            with db_transaction():
                Messages.delete().where(Messages.id == id).execute()
            return make_response(('deleted'), 200)
        except Exception as e:
            logger.exception("Unable to delete the banner: " + str(e))
            return make_response(json.dumps({'message': 'Unable to delete the banner'}), 500)


