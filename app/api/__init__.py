"""REST API for mobile apps and other programs: /api/v2.

Sign in once with POST /api/v2/tokens (username + password) to get a personal
access token, then send it on every request:  Authorization: Bearer qg_...
Every action goes through the same code as the web pages (app/qgen/services.py
and app/messages/services.py). The description for app developers is at
/api/v2/openapi.json and /api/v2/docs.
"""
from flask import Blueprint

api_bp = Blueprint('apiv2', __name__, url_prefix='/api/v2', template_folder='templates')

from app.api import auth, errors, tokens, student, teacher, docs  # noqa: E402,F401
