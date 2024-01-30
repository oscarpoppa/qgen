from flask import Blueprint

qgen_bp = Blueprint('qgen', __name__)

from app.qgen import routes
