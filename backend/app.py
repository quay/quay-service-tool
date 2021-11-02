from flask import Flask, request
from flask_restful import Api
from flask_login import LoginManager
import pymysql
import psycopg2
from urllib.parse import unquote
import os
from tasks.banner import BannerTask
from tasks.username import UsernameTask
import yaml
from keycloak import KeycloakOpenID
from utils import *


app = Flask(__name__, static_folder='/backend/static', static_url_path='/')
api = Api(app)

login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def user_loader(user_id):
    """Given *user_id*, return the associated User object.

    :param unicode user_id: user_id (email) user to retrieve

    """
    print("In user loader")
    return
    # return User.query.get(user_id)

@login_manager.request_loader
def load_user_from_request(request):
    api_key = request.headers.get('Authorization')
    bearer_token = api_key.replace('Bearer ', '', 1)
    # Configure client
    keycloak_openid = KeycloakOpenID(server_url="http://localhost:8081/auth/",
                                     client_id="quay-service-tool",
                                     realm_name="Demo")
    try:
        userinfo = keycloak_openid.userinfo(bearer_token)
        authenticate_email(userinfo.get("email"))
        if userinfo.get("email") == "sdadi@redhat.com":
            print("I am here!")
    except TypeError:
        pass
    return
    # return User.query.filter_by(api_key=header_val).first()


with open(os.environ.get('CONFIG_PATH') + "/config.yaml") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)
    app.config.update(config)

password_decoded = unquote(app.config.get('db', {}).get('password'))
@app.route("/")
def main():
    return app.send_static_file('index.html')

api.add_resource(BannerTask, '/banner', '/banner/<int:id>', endpoint='banner')
api.add_resource(UsernameTask, '/username')

@app.before_request
def before_request():
    if app.config.get('is_local'):
        request.db = psycopg2.connect(host=app.config.get('db', {}).get('host'), database=app.config.get('db', {}).get('name'), user=app.config.get('db', {}).get('user'), password=password_decoded)
    else:
        request.db = pymysql.connect(host=app.config.get('db', {}).get('host'), database=app.config.get('db', {}).get('name'), user=app.config.get('db', {}).get('user'), password=password_decoded)

@app.teardown_request
def teardown_request(exception):
    if hasattr(request, 'db'):
        request.db.close()

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
