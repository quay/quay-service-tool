import json

from flask import make_response
from flask_login import login_required
from flask_restful import Resource, reqparse

from utils import log_response, verify_admin_permissions

from data.model import user, organization, team, InvalidOrganizationException
from data.model.team import UserAlreadyInTeam
from data.database import Team, TeamRole


class AddOrgOwnerTask(Resource):
    @log_response
    @verify_admin_permissions
    @login_required
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("username", type=str, help="username to add as owner")
        parser.add_argument("organization", type=str, help="organization name")
        args = parser.parse_args()

        username = args.get('username')
        org_name = args.get('organization')

        if not username:
            return make_response(
                json.dumps({"message": "Parameter 'username' required"}), 400
            )

        if not org_name:
            return make_response(
                json.dumps({"message": "Parameter 'organization' required"}), 400
            )

        # Look up user
        found_user = user.get_namespace_user(username)
        if found_user is None:
            return make_response(
                json.dumps({"message": f"User {username} not found"}), 404
            )

        if found_user.organization:
            return make_response(
                json.dumps({"message": f"{username} is an organization, not a user"}), 400
            )

        # Look up organization
        try:
            org_obj = organization.get_organization(org_name)
        except InvalidOrganizationException:
            return make_response(
                json.dumps({"message": f"Organization {org_name} not found"}), 404
            )

        # Add user to admin team
        try:
            admin_role = TeamRole.get(name="admin")
            admin_team = (
                Team.select().where(Team.role == admin_role, Team.organization == org_obj).get()
            )
            team.add_user_to_team(found_user, admin_team)
        except UserAlreadyInTeam:
            return make_response(
                json.dumps({"message": f"User {username} is already an owner of {org_name}"}), 400
            )

        return make_response(
            json.dumps(
                {
                    "message": f"User {username} added as owner of {org_name}",
                    "username": username,
                    "organization": org_name,
                }
            ),
            200,
        )
