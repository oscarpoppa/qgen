from flask import Blueprint
from app import db

qgen_bp = Blueprint('qgen', __name__, template_folder='templates')

from app.qgen import routes
