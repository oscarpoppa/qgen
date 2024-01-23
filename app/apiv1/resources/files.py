from flask_restful import Resource
from os import listdir

class Files(Resource):
    def get(self):
        all = listdir('/home/dan/proj/quiz/app/static')
        return all, 200
