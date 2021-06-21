from flask import Flask, request
from flask_restful import Api
from typing import final
import pymysql
import psycopg2
from urllib.parse import unquote
import os
from tasks.banner import BannerTask
from tasks.username import UsernameTask

app = Flask(__name__)
api = Api(app)
password_decoded = unquote(os.environ.get('DB_PASSWORD'))

@app.route("/")
def main():
    return "Quay Service Tool Backend"

api.add_resource(BannerTask, '/banner', '/banner/<int:id>', endpoint='banner')
api.add_resource(UsernameTask, '/username')

@app.before_request
def before_request():
    request.db = psycopg2.connect(host=os.environ.get('DB_HOST'), port = os.environ.get('DB_PORT'), database=os.environ.get('DB_NAME'), user=os.environ.get('DB_USER'), password=password_decoded)

@app.teardown_request
def teardown_request(exception):
    request.db.close()
    

if __name__ == '__main__':
    app.run(debug=True)
