from flask import current_app
from flask_restful import Resource
from os import listdir, path

from . import teacher_token

#endpoint to list uploaded files (teachers only)
class Files(Resource):
    method_decorators = [teacher_token]

    def get(self):
        folder = current_app.config['STATIC_DIR']
        return sorted(f for f in listdir(folder) if path.isfile(path.join(folder, f))), 200
