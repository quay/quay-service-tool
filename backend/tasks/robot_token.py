import json
from typing import Union

from flask import make_response
from flask_login import login_required
from flask_restful import Resource, reqparse

from backend.utils import log_response, verify_admin_permissions

from data.model import user, organization, InvalidOrganizationException, DataModelException, InvalidRobotException


class RobotTokenTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("token", type=str, help="raw token")
        parser.add_argument("name", type=str, help="token name")
        parser.add_argument("organization", type=str, help="organization name")
        args = parser.parse_args()

        robot_name = args.get('name')
        org = args.get('organization')
        token = args.get('token')

        # Check params
        if not robot_name:
            return make_response(
                json.dumps({"message": "Parameter 'robot_name' required"}), 400
            )

        if not org:
            return make_response(
                json.dumps({"message": "Parameter 'organization' required"}), 400
            )

        if not token:
            return make_response(
                json.dumps({"message": "Parameter 'token' required"}), 400
            )

        try:
            parent = organization.get_organization(org)
        except InvalidOrganizationException as e:
            return make_response(
                json.dumps({"message": "Parameter 'token' required"}), 404
            )

        try:
            user.create_robot(robot_shortname=robot_name, parent=parent)
        except Union[DataModelException, InvalidRobotException] as e:
            return make_response(
                json.dumps({"message": f"ERROR: {e}"}), 400
            )

        return make_response(
            json.dumps(
                {
                    "message": "Robot token created",
                    "robot_name": robot_name,
                    "organization": org,
                }
            ),
            200,
        )
