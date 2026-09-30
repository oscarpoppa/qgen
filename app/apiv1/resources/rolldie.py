from flask_restful import Resource
from random import randint

from . import teacher_token

#endpoint to return a die-roll result (teachers only)
class DieRoll(Resource):
    method_decorators = [teacher_token]

    def get(self):
        return randint(1,6), 200
