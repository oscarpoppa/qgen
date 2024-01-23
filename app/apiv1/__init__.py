from flask_restful import Api
from flask import Blueprint
from app.apiv1.resources.user import ListUsers
from app.apiv1.resources.files import Files
from app.apiv1.resources.rolldie import DieRoll

api_bp = Blueprint('api', __name__)
api = Api(api_bp, prefix='/api/v1')

api.add_resource(ListUsers, '/users')
api.add_resource(Files, '/files')
api.add_resource(DieRoll, '/dieroll')
