from flask import request
from flask_restful import Resource
from psycopg2.extras import RealDictCursor
from pymysql.cursors import DictCursor
import os

def is_valid_severity(severity):
    return severity in ["default", "success", "info", "danger", "warning"]

class User(object):
    def __init__(self, is_authenticated=False, email=None):
        self.email = email
        self.is_authenticated = is_authenticated

class Auth(Resource):

    def authenticate_email(email):
        # Check for email in DB
        if not email:
            return User()

        if email.split("@")[1] != "redhat.com":
            return User()

        with request.db.cursor(cursor_factory=RealDictCursor) if os.environ.get('IS_LOCAL') else request.db.cursor(DictCursor) as cur:
            # TODO: Add logic to select user
            cur.execute("SELECT * from \"user\" where email = %s", (email,))
            result = cur.fetchall()
            request.db.commit()
            return User(is_authenticated=True if result else False, email=email)
        return User()
