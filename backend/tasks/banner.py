import logging
from flask_login import login_required
from flask_restful import Resource
from flask import make_response
from flask_restful import reqparse
from playhouse.shortcuts import model_to_dict
from utils import is_valid_severity, AppLogger
import json
from data.model import message, db_transaction
from data.database import Messages


class BannerTask(Resource):
    @login_required
    def get(self):
        try:
            messages = {"messages": [model_to_dict(m) for m in message.get_messages()]}
            response = json.dumps(messages)
            AppLogger.info(args=None, response=response)
            return make_response(response, 200)
        except Exception as e:
            AppLogger.exception(
                args=None,
                response=f"Unable to fetch banners: {str(e)}",
            )
            return make_response(
                json.dumps({"message": "Unable to fetch banners"}), 500
            )

    @login_required
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("message", type=str, help="banner message")
        parser.add_argument("severity", type=str, help="severity")
        args = parser.parse_args()
        content = args.get("message")
        severity = args.get("severity")

        if not is_valid_severity(severity):
            response = "Invalid severity value"
            AppLogger.error(
                args=json.dumps(args), response=response
            )
            return make_response(json.dumps({"message": response}), 400)

        try:
            with db_transaction():
                message.create(
                    [
                        {
                            "content": content,
                            "severity": severity,
                            "media_type": "text/markdown",
                        }
                    ]
                )
            response = "Banner created"
            AppLogger.info(
                args=json.dumps(args), response=response
            )
            return make_response(json.dumps({"message": response}), 201)
        except Exception as e:
            AppLogger.exception(
                args=json.dumps(args),
                response=f"Unable to create a new banner: {str(e)}",
            )
            return make_response(
                json.dumps({"message": "Unable to create a new banner"}), 500
            )

    @login_required
    def put(self):
        parser = reqparse.RequestParser()
        parser.add_argument("message", type=str, help="banner message")
        parser.add_argument("severity", type=str, help="severity")
        parser.add_argument("id", type=str, help="banner id")
        args = parser.parse_args()
        content = args.get("message")
        severity = args.get("severity")
        id = args.get("id")

        if not is_valid_severity(severity):
            response = "Invalid severity value"
            AppLogger.error(
                args=json.dumps(args), response=response
            )
            return make_response(json.dumps({"message": response}), 400)
        if content == "" or severity == "":
            response = "Fields severity and message required"
            AppLogger.error(
                args=json.dumps(args), response=response
            )
            return make_response(json.dumps({"message": response}), 400)

        try:
            with db_transaction():
                Messages.update({"content": content, "severity": severity}).where(
                    Messages.id == id
                ).execute()
            response = "updated"
            AppLogger.info(
                args=json.dumps(args), response=response
            )
            return make_response(response, 200)
        except Exception as e:
            AppLogger.exception(
                args=json.dumps(args),
                response=f"Unable to update the banner:  {str(e)}",
            )
            return make_response(
                json.dumps({"message": "Unable to update the banner"}), 500
            )

    @login_required
    def delete(self, id):
        try:
            Messages.get(Messages.id == id)
        except Messages.DoesNotExist:
            response = "Banner not found"
            AppLogger.exception(args=id, response=response)
            return make_response(response, 404)
        except Exception as e:
            AppLogger.exception(
                args=id,
                response=f"Unable to check banner existence: {str(e)}",
            )
            return make_response(
                json.dumps({"message": "Unable to check banner existence"}), 500
            )

        try:
            with db_transaction():
                Messages.delete().where(Messages.id == id).execute()
            response = "deleted"
            AppLogger.info(args=id, response=response)
            return make_response(response, 200)
        except Exception as e:
            AppLogger.exception(
                args=id,
                response=f"Unable to delete the banner: {str(e)}",
            )
            return make_response(
                json.dumps({"message": "Unable to delete the banner"}), 500
            )
