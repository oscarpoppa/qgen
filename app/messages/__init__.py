from flask import Blueprint
from app import db

messages_bp = Blueprint('messages', __name__, template_folder='templates')

from app.messages import routes
