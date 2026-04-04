from flask import Blueprint

sandbox_bp = Blueprint('sandbox', __name__, template_folder='templates')

from . import routes
