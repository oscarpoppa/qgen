from flask import Blueprint
from app import db

error_bp = Blueprint('error', __name__, template_folder='templates')

from app.error import handlers
