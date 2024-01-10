from flask import Blueprint

error_bp = Blueprint('error', __name__, template_folder='templates')

from app.error import handlers
