from flask_restful import Resource, Api


class BannerTask(Resource):
    def get(self):
        return {'banner': 'Current banner'}


