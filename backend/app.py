from flask import Flask, request, render_template, make_response, jsonify
from flask_restful import Api
from flask_login import LoginManager
from keycloak import KeycloakOpenID
from prometheus_flask_exporter import PrometheusMetrics

from urllib.parse import unquote

from tasks.robot_token import RobotTokenTask
from tasks.org_owner import AddOrgOwnerTask
from tasks.banner import BannerTask
from tasks.username import UsernameTask
from tasks.federateduser import FederatedUserTask
from tasks.user import UserTask, FetchUserFromEmailTask, FetchUserFromNameTask, UpdateEmailTask, FetchUserFromStripeID
import yaml
import logging
from utils import *
from data import database
import os

logging.basicConfig()
logging.root.setLevel(logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='/backend/static', static_url_path='/')
api = Api(app)
metrics = PrometheusMetrics(app)


login_manager = LoginManager()
login_manager.init_app(app)


with open(os.environ.get('CONFIG_PATH') + "/config.yaml") as f:
    print("Reading config from: %s", os.environ.get('CONFIG_PATH') + "/config.yaml")
    config = yaml.load(f, Loader=yaml.FullLoader)
    app.config.update(config)


@login_manager.request_loader
def load_user_from_request(request):
    if request.path != "/" and \
            ((not app.config.get('is_local') and os.environ.get("TESTING") is None) or \
            # used to test authentication on dev env
            (app.config.get('is_local') and app.config.get('test_auth'))):
        try:
            api_key = request.headers.get('Authorization')
            bearer_token = api_key.replace('Bearer ', '', 1)
            keycloak_openid = KeycloakOpenID(
                                            server_url=app.config.get('authentication', {}).get('url'),
                                            client_id=app.config.get('authentication', {}).get('clientid'),
                                            realm_name=app.config.get('authentication', {}).get('realm'),
                                        )

            keycloak_public_key = "-----BEGIN PUBLIC KEY-----\n" + keycloak_openid.public_key() + "\n-----END PUBLIC KEY-----"
            options = {"verify_signature": True, "verify_aud": True, "verify_exp": True}
            if app.config.get('is_local'):
                options['verify_aud'] = False
            token_info = keycloak_openid.decode_token(bearer_token, key=keycloak_public_key, options=options)
            return Auth.authenticate_user(token_info, app.config.get('authentication'))
        except Exception as e:
            logging.exception(e)
            return make_response("Error occured while authentication: ", str(e), 500)
    else:
        return User(email="local-dev@testing.com", username="Local Dev", is_authenticated=True)


def create_transaction(db):
    return db.transaction()
conn_args = app.config.get("DB_CONNECTION_ARGS",{})
conn_args["threadlocals"] = True
conn_args["autorollback"] = True
app.config["DB_CONNECTION_ARGS"] = conn_args
app.config["DB_TRANSACTION_FACTORY"] = create_transaction
database.configure(app.config)


@app.route("/healthcheck")
def healthcheck():
    try:
        database.db.connect()
        database.db.execute_sql("SELECT 1")
        database.db.close()
        return make_response(jsonify({'message': 'Healthy'}), 200)
    except Exception as e:
        if database.db.obj is not None and not database.db.is_closed():
            logging.info("Closing database connection")
            database.db.close()
        return make_response(jsonify({'message': 'DB is not up: {}'.format(str(e))}), 503)


@app.route("/")
def main():
    AUTH_URL = app.config.get('authentication', {}).get('url')
    AUTH_REALM = app.config.get('authentication', {}).get('realm')
    AUTH_CLIENTID = app.config.get('authentication', {}).get('clientid')
    ADMIN_ROLE = app.config.get('authentication', {}).get('roles', {}).get('ADMIN_ROLE')
    EXPORT_COMPLIANCE_ROLE = app.config.get('authentication', {}).get('roles', {}).get('EXPORT_COMPLIANCE_ROLE')
    return render_template('index.html', AUTH_URL=AUTH_URL,  AUTH_REALM=AUTH_REALM, AUTH_CLIENTID=AUTH_CLIENTID,
                           ADMIN_ROLE=ADMIN_ROLE, EXPORT_COMPLIANCE_ROLE=EXPORT_COMPLIANCE_ROLE,)


api.add_resource(BannerTask, '/banner', '/banner/<int:id>', endpoint='banner')
api.add_resource(UsernameTask, '/username')
api.add_resource(UserTask, '/user/<username>')
api.add_resource(FetchUserFromStripeID, '/user/stripe/<stripe_id>')
api.add_resource(FetchUserFromNameTask, '/quayusername/<quayusername>')
api.add_resource(FetchUserFromEmailTask, '/quayuseremail/<quayuseremail>')
api.add_resource(FederatedUserTask, '/federateduser/<username>')
api.add_resource(UpdateEmailTask, '/user/email')
api.add_resource(RobotTokenTask, '/robot/token')
api.add_resource(AddOrgOwnerTask, '/org/owner')

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
