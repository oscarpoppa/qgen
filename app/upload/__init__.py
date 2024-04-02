from flask import Blueprint

upload_bp = Blueprint('upload', __name__, template_folder='templates')

from . import routes
