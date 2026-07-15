import base64
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
from tasks.spam_detection import (
    SpamAuditTask,
    SpamClassifierImportCsvTask,
    SpamClassifierListTask,
    SpamClassifierTask,
    SpamClassifierExportArtifactTask,
    SpamClassifierTrainTask,
    SpamDetectionHealthTask,
    SpamPolicyTask,
    SpamPreviewTask,
    SpamReviewDismissTask,
    SpamReviewQuarantineTask,
    SpamReviewRedactTask,
    SpamReviewRestoreTask,
    SpamReviewTask,
    SpamRunMatchesTask,
    SpamRunsTask,
    SpamTrainingExamplesTask,
)
import yaml
import logging
from utils import *
from util.marketplace import MarketplaceUserApi
from data import database
import os
from spam_detection import DEFAULT_QUARANTINE_DESCRIPTION

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

app.config.setdefault("SPAM_DETECTION_STATE_DB_URI", "sqlite:///spam_detection_state.db")
app.config.setdefault("SPAM_DETECTION_BATCH_SIZE", 200)
app.config.setdefault("SPAM_DETECTION_SLEEP_BETWEEN_BATCHES", 0.5)
app.config.setdefault("SPAM_DETECTION_SCAN_DRY_RUN", True)
app.config.setdefault("SPAM_DETECTION_MAX_REPOS", 0)
app.config.setdefault("SPAM_DETECTION_API_SCAN_LIMIT", 10000)
app.config.setdefault("SPAM_DETECTION_MAX_TRAINING_TEXT_LENGTH", 10000)
app.config.setdefault("SPAM_DETECTION_INCLUDE_PRIVATE", False)
app.config.setdefault(
    "SPAM_DETECTION_QUARANTINE_DESCRIPTION",
    DEFAULT_QUARANTINE_DESCRIPTION,
)


@login_manager.request_loader
def load_user_from_request(request):
    if request.path != "/" and \
            ((not app.config.get('is_local') and os.environ.get("TESTING") is None) or \
            # used to test authentication on dev env
            (app.config.get('is_local') and app.config.get('test_auth'))):
        try:
            api_key = request.headers.get('Authorization')
            if not api_key:
                return User()
            bearer_token = api_key.replace('Bearer ', '', 1)
            keycloak_openid = KeycloakOpenID(
                                            server_url=app.config.get('authentication', {}).get('url'),
                                            client_id=app.config.get('authentication', {}).get('clientid'),
                                            realm_name=app.config.get('authentication', {}).get('realm'),
                                        )

            check_claims = {}
            if not app.config.get('is_local'):
                check_claims["aud"] = app.config.get('authentication', {}).get('clientid')
            token_info = keycloak_openid.decode_token(bearer_token, check_claims=check_claims)
            return Auth.authenticate_user(token_info, app.config.get('authentication'))
        except Exception as e:
            logging.exception(e)
            return User()
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

# Write marketplace certs from config to disk so MarketplaceUserApi
# can read them from the expected paths (/conf/stack/quay-marketplace-api.{crt,key}).
# In production, these values come from the app-interface secret config.
from util.marketplace import MARKETPLACE_FILE, MARKETPLACE_SECRET

for config_key, file_path in [
    ("MARKETPLACE_CERT", MARKETPLACE_FILE),
    ("MARKETPLACE_KEY", MARKETPLACE_SECRET),
]:
    content = app.config.get(config_key)
    if content:
        content = base64.b64decode(content)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)
        os.chmod(file_path, 0o600)
        logger.info("Wrote %s from config", file_path)

marketplace_users = MarketplaceUserApi(app)


@app.route("/healthcheck")
def healthcheck():
    try:
        database.db.connect()
        database.db.execute_sql("SELECT 1")
        database.db.close()
        return make_response(jsonify({'message': 'Healthy'}), 200)
    except Exception as e:
        logger.error("Healthcheck failed", exc_info=True)
        if database.db.obj is not None and not database.db.is_closed():
            logger.info("Closing database connection")
            database.db.close()
        return make_response(jsonify({'message': 'Service unavailable'}), 503)


@app.route("/")
def main():
    AUTH_URL = app.config.get('authentication', {}).get('url')
    AUTH_REALM = app.config.get('authentication', {}).get('realm')
    AUTH_CLIENTID = app.config.get('authentication', {}).get('clientid')
    ADMIN_ROLE = app.config.get('authentication', {}).get('roles', {}).get('ADMIN_ROLE')
    EXPORT_COMPLIANCE_ROLE = app.config.get('authentication', {}).get('roles', {}).get('EXPORT_COMPLIANCE_ROLE')
    SPAM_DETECTION_ROLE = app.config.get('authentication', {}).get('roles', {}).get('SPAM_DETECTION_ROLE')
    SPAM_DETECTION_REMEDIATION_ROLE = app.config.get('authentication', {}).get('roles', {}).get('SPAM_DETECTION_REMEDIATION_ROLE')
    return render_template('index.html', AUTH_URL=AUTH_URL,  AUTH_REALM=AUTH_REALM, AUTH_CLIENTID=AUTH_CLIENTID,
                           ADMIN_ROLE=ADMIN_ROLE, EXPORT_COMPLIANCE_ROLE=EXPORT_COMPLIANCE_ROLE,
                           SPAM_DETECTION_ROLE=SPAM_DETECTION_ROLE,
                           SPAM_DETECTION_REMEDIATION_ROLE=SPAM_DETECTION_REMEDIATION_ROLE,)


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
api.add_resource(SpamDetectionHealthTask, '/spam-detection/health')
api.add_resource(SpamClassifierListTask, '/spam-detection/classifiers')
api.add_resource(SpamClassifierTask, '/spam-detection/classifiers/<classifier_uuid>')
api.add_resource(SpamTrainingExamplesTask, '/spam-detection/classifiers/<classifier_uuid>/training-examples')
api.add_resource(SpamClassifierImportCsvTask, '/spam-detection/classifiers/<classifier_uuid>/import-csv')
api.add_resource(SpamClassifierTrainTask, '/spam-detection/classifiers/<classifier_uuid>/train')
api.add_resource(SpamClassifierExportArtifactTask, '/spam-detection/classifiers/<classifier_uuid>/export-artifact')
api.add_resource(SpamPolicyTask, '/spam-detection/policy')
api.add_resource(SpamPreviewTask, '/spam-detection/preview')
api.add_resource(SpamRunsTask, '/spam-detection/runs')
api.add_resource(SpamRunMatchesTask, '/spam-detection/runs/<run_uuid>/matches')
api.add_resource(SpamReviewTask, '/spam-detection/review')
api.add_resource(SpamAuditTask, '/spam-detection/audit')
api.add_resource(SpamReviewQuarantineTask, '/spam-detection/review/<record_uuid>/quarantine')
api.add_resource(SpamReviewRestoreTask, '/spam-detection/review/<record_uuid>/restore')
api.add_resource(SpamReviewDismissTask, '/spam-detection/review/<record_uuid>/dismiss')
api.add_resource(SpamReviewRedactTask, '/spam-detection/review/<record_uuid>/redact')

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
