from flask_restful import Resource
from flask import request
from flask_login import current_user
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


def is_valid_severity(severity):
    return severity in ["default", "success", "info", "danger", "warning"]


class User(object):
    def __init__(self, is_authenticated=False, email=None, username=None):
        self.email = email
        self.username = username
        self.is_authenticated = is_authenticated


class Auth(Resource):
    def authenticate_user(token_info, config):
        if not token_info or not token_info.get("realm_access"):
            return User()

        realm_access = token_info["realm_access"]
        if not realm_access.get("roles") or not config["roles"] or \
           not (set(realm_access["roles"]) & set(config["roles"].values())):
            return User()

        return User(
            email=token_info["email"],
            username=token_info["name"],
            is_authenticated=True,
        )


def create_transaction(db):
    if type(db.obj).__name__ == "ObservableRetryingMySQLDatabase":
        try:
            db.close()
        except:
            pass

    return db.transaction()


def log_response(func):
    def wrapper(*args, **kwargs):
        response = func(*args, **kwargs)
        log_fn = logging.error
        if response.status_code == 500:
            log_fn = logging.exception
        if response.status_code == 200 or response.status_code == 201:
            log_fn = logging.info
        log_fn(
            f"{datetime.utcnow().strftime('%d %b, %Y, %H:%M:%S')} - "
            f"{request.method} - "
            f"{request.path} - "
            f"{response.status_code} - "
            f"{current_user.username} - "
            f"{current_user.email} - "
            f"{json.dumps(request.json)} - "
            f"{response.data}"
        )
        return response

    return wrapper
