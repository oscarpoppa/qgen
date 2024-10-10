from flask_restful import Resource
from random import randint

#endpoint to return a die-roll result 
class DieRoll(Resource):
    def get(self):
        return randint(1,6), 200
