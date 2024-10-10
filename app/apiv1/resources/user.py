from app.user.models import User
from flask_restful import Resource, fields, marshal_with

user_fields = {'username': fields.String,
               'email': fields.String}

#endpoint to list users
class ListUsers(Resource):
    @marshal_with(user_fields)
    def get(self):
        return [{'username': u.username, 'email':u.email} for u in User.query.all()], 200


