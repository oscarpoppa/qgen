from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
migrate = Migrate(app, db) 
login = LoginManager(app)
login.login_view = 'login'

# this needs to be down here to avoid circular import
from app.error import error_bp
from app.apiv1 import api_bp

app.register_blueprint(error_bp)
app.register_blueprint(api_bp)

# this needs to be down here to avoid circular import
from app import routes, models
from app.qgen import models
from app.qgen import routes
