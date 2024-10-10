from flask_restful import Resource
from os import listdir

#endpoint to list files
class Files(Resource):
    def get(self):
        all = listdir('/home/dan/proj/quiz/app/static')
        return all, 200
