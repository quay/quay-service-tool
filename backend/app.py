from flask import Flask, request, render_template, make_response, jsonify
from flask_restful import Api
from flask_login import LoginManager
from keycloak import KeycloakOpenID
from prometheus_flask_exporter import PrometheusMetrics

import pymysql
import psycopg2
from urllib.parse import unquote
from tasks.banner import BannerTask
from tasks.username import UsernameTask
from tasks.user import UserTask
import yaml
import logging
from utils import *


app = Flask(__name__, static_folder='/backend/static', static_url_path='/')
api = Api(app)
metrics = PrometheusMetrics(app)


login_manager = LoginManager()
login_manager.init_app(app)


with open(os.environ.get('CONFIG_PATH') + "/config.yaml") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)
    print("loading config: %s", config)
    app.config.update(config)


@login_manager.request_loader
def load_user_from_request(request):
    if request.path != "/" and not app.config.get('is_local') and os.environ.get("TESTING") is None:
        try:
            api_key = request.headers.get('Authorization')
            bearer_token = api_key.replace('Bearer ', '', 1)
            keycloak_openid = KeycloakOpenID(
                                            server_url=app.config.get('authentication', {}).get('url'),
                                            client_id=app.config.get('authentication', {}).get('clientid'),
                                            realm_name=app.config.get('authentication', {}).get('realm')
                                        )

            keycloak_public_key = "-----BEGIN PUBLIC KEY-----\n" + keycloak_openid.public_key() + "\n-----END PUBLIC KEY-----"
            options = {"verify_signature": True, "verify_aud": True, "verify_exp": True}
            token_info = keycloak_openid.decode_token(bearer_token, key=keycloak_public_key, options=options)
            return Auth.authenticate_user(token_info, app.config.get('authentication'))
        except Exception as e:
            logging.exception(e)
            return make_response("Error occured while authentication: ", str(e), 500)
    else:
        return User(is_authenticated=True)


password_decoded = unquote(app.config.get('db', {}).get('password'))


@app.route("/healthcheck")
def healthcheck():
    try:
        with request.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if os.environ.get('IS_LOCAL') else request.db.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SELECT 1')
            return make_response(jsonify({'message': 'Healthy'}), 200)
    except Exception as e:
        return make_response(jsonify({'message': 'DB is not up: {}'.format(str(e))}), 503)


@app.route("/")
def main():
    AUTH_URL = app.config.get('authentication', {}).get('url')
    AUTH_REALM = app.config.get('authentication', {}).get('realm')
    AUTH_CLIENTID = app.config.get('authentication', {}).get('clientid')
    return render_template('index.html', AUTH_URL=AUTH_URL,  AUTH_REALM=AUTH_REALM, AUTH_CLIENTID=AUTH_CLIENTID)


api.add_resource(BannerTask, '/banner', '/banner/<int:id>', endpoint='banner')
api.add_resource(UsernameTask, '/username')
api.add_resource(UserTask, '/user/<user>')


@app.before_request
def before_request():
    if app.config.get('is_local') and os.environ.get("TESTING") is None:
        request.db = psycopg2.connect(host=app.config.get('db', {}).get('host'), database=app.config.get('db', {}).get('name'), user=app.config.get('db', {}).get('user'), password=password_decoded)
    else:
        request.db = pymysql.connect(host=app.config.get('db', {}).get('host'), database=app.config.get('db', {}).get('name'), user=app.config.get('db', {}).get('user'), password=password_decoded)


@app.teardown_request
def teardown_request(exception):
    if hasattr(request, 'db'):
        request.db.close()


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
