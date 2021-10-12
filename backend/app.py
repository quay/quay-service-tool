from flask import Flask, request
from flask_restful import Api
import pymysql
import psycopg2
from urllib.parse import unquote
import os
from flask_basicauth import BasicAuth
from tasks.banner import BannerTask
from tasks.username import UsernameTask
import yaml

app = Flask(__name__, static_folder='/backend/static', static_url_path='/')
api = Api(app)

with open(os.environ.get('CONFIG_PATH') + "/config.yaml") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)
    app.config.update(config)

app.config['BASIC_AUTH_USERNAME'] = app.config.get('basic_auth', {}).get('username')
app.config['BASIC_AUTH_PASSWORD'] = app.config.get('basic_auth', {}).get('password')
app.config['BASIC_AUTH_FORCE'] = app.config.get('basic_auth', {}).get('force')
basic_auth = BasicAuth(app)

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
