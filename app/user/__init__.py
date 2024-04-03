from flask import Blueprint
from app import db, login

user_bp = Blueprint('user', __name__, template_folder='templates')

from . import routes
