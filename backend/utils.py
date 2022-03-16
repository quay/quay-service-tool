import os
from flask_restful import Resource


def is_valid_severity(severity):
    return severity in ["default", "success", "info", "danger", "warning"]


class User(object):
    def __init__(self, is_authenticated=False, email=None):
        self.email = email
        self.is_authenticated = is_authenticated


class Auth(Resource):
    def authenticate_user(token_info, config):
        if not token_info or not token_info.get("realm_access"):
            return User()

        realm_access = token_info["realm_access"]

        if not realm_access.get("roles") or config["role"] not in realm_access["roles"]:
            return User()

        return User(is_authenticated=True)


def create_transaction(db):
    if type(db.obj).__name__ == "ObservableRetryingMySQLDatabase":
        try:
            db.close()
        except:
            pass

    return db.transaction()
