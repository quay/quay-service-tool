from flask_restful import Resource
from flask import request, make_response
from flask import current_app as app
from flask_login import current_user
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


def is_valid_severity(severity):
    return severity in ["default", "success", "info", "danger", "warning"]


class User(object):
    def __init__(self, is_authenticated=False, email=None, username=None, realm_access=None):
        self.email = email
        self.username = username
        self.is_authenticated = is_authenticated
        self.realm_access = realm_access


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
            realm_access=realm_access,
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


def verify_admin_permissions(func):
    def wrapper(*args, **kwargs):
        # Bypassing checks for local dev when auth is not on
        if app.config.get('is_local') and not app.config.get('test_auth'):
            return func(*args, **kwargs)

        if not current_user or not current_user.realm_access:
            return make_response(json.dumps({"message": "No RBAC defined for user"}), 401)

        ADMIN_ROLE = app.config.get('authentication', {}).get('roles', {}).get('ADMIN_ROLE')
        if ADMIN_ROLE not in current_user.realm_access.get('roles', None):
            return make_response(json.dumps({"message": "Require ADMIN permissions to perform action"}), 401)

        response = func(*args, **kwargs)
        return response
    return wrapper


def verify_export_compliance_permissions(func):
    def wrapper(*args, **kwargs):
        # Bypassing checks for local dev when auth is not on
        if app.config.get('is_local') and not app.config.get('test_auth'):
            return func(*args, **kwargs)

        if not current_user or not current_user.realm_access:
            return make_response(json.dumps({"message": "No RBAC defined for user"}), 401)

        EXPORT_COMPLIANCE_ROLE = app.config.get('authentication', {}).get('roles', {}).get('EXPORT_COMPLIANCE_ROLE')
        if EXPORT_COMPLIANCE_ROLE not in current_user.realm_access.get('roles', None):
            return make_response(json.dumps({"message": "Require EXPORT_COMPLIANCE_ROLE permissions to perform action"}), 401)

        response = func(*args, **kwargs)
        return response
    return wrapper


def verify_admin_or_export_perm(func):
    def wrapper(*args, **kwargs):
        # Bypassing checks for local dev when auth is not on
        if app.config.get('is_local') and not app.config.get('test_auth'):
            return func(*args, **kwargs)

        if not current_user or not current_user.realm_access:
            return make_response(json.dumps({"message": "No RBAC defined for user"}), 401)

        ADMIN_ROLE = app.config.get('authentication', {}).get('roles', {}).get('ADMIN_ROLE')
        EXPORT_COMPLIANCE_ROLE = app.config.get('authentication', {}).get('roles', {}).get('EXPORT_COMPLIANCE_ROLE')
        if not (set([ADMIN_ROLE, EXPORT_COMPLIANCE_ROLE]) & set(current_user.realm_access.get('roles', None))):
            return make_response(json.dumps({"message": f"Not enough permissions to perform action"}), 401)

        response = func(*args, **kwargs)
        return response
    return wrapper
