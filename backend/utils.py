from flask_restful import Resource, reqparse
from flask_login import current_user
from datetime import datetime
import logging

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

        if not realm_access.get("roles") or config["role"] not in realm_access["roles"]:
            return User()

        return User(email=token_info["email"], username=token_info["name"], is_authenticated=True)


def create_transaction(db):
    if type(db.obj).__name__ == "ObservableRetryingMySQLDatabase":
        try:
            db.close()
        except:
            pass

    return db.transaction()


class AppLogger(object):

    @staticmethod
    def log_info(args, response):
        logger.info(
            f"{reqparse.request.method} - "
            f"{reqparse.request.endpoint} - "
            f"{current_user.username} - "
            f"{current_user.email} - "
            f"{args} - "
            f"{response} - "
            f"{datetime.utcnow().strftime('%d %b, %Y, %H:%M:%S')}"
        )

    @staticmethod
    def log_error(args, response):
        logger.error(
            f"{reqparse.request.method} - "
            f"{reqparse.request.endpoint} - "
            f"{current_user.username} - "
            f"{current_user.email} - "
            f"{args} - "
            f"{response} - "
            f"{datetime.utcnow().strftime('%d %b, %Y, %H:%M:%S')}"
        )

    @staticmethod
    def log_exception(args, response):
        logger.exception(
            f"{reqparse.request.method} - "
            f"{reqparse.request.endpoint} - "
            f"{current_user.username} - "
            f"{current_user.email} - "
            f"{args} - "
            f"{response} - "
            f"{datetime.utcnow().strftime('%d %b, %Y, %H:%M:%S')}"
        )
