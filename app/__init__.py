from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

app = Flask(__name__)
app.config.from_object(Config)
app.logger.setLevel(3)
db = SQLAlchemy(app)
migrate = Migrate(app, db) 
login = LoginManager(app)
login.login_view = 'login'

# this needs to be down here to avoid circular import
from app.error import error_bp
from app.apiv1 import api_bp
from app.qgen import qgen_bp
from app.commands import dbdump as dbdump_cli_group

app.cli.add_command(dbdump_cli_group, name='dbdump')

app.register_blueprint(error_bp)
app.register_blueprint(api_bp)
app.register_blueprint(qgen_bp)

# this needs to be down here to avoid circular import
from app import routes, models, commands
from app.qgen import models
