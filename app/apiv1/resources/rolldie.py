from flask_restful import Resource
from random import randint

class DieRoll(Resource):
    def get(self):
        return randint(1,6), 200
