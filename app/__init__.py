from flask import Flask
import click
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

#build app
app = Flask(__name__, static_folder=Config.STATIC_DIR)
app.config.from_object(Config)
#uploads (pictures, files) are refused above this size
app.config.setdefault('MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
app.logger.setLevel(3)
db = SQLAlchemy(app)

#SQLite (tests, local dev) ignores foreign keys unless asked; MySQL always enforces them
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

@event.listens_for(Engine, 'connect')
def _sqlite_foreign_keys(dbapi_conn, record):
    if isinstance(dbapi_conn, sqlite3.Connection):
        cur = dbapi_conn.cursor()
        cur.execute('PRAGMA foreign_keys=ON')
        cur.close()
migrate = Migrate(app, db) 
login = LoginManager(app)
login.login_view = 'user.login'

#gather and register blueprints
from app.error import error_bp
from app.apiv1 import api_bp
from app.qgen import qgen_bp
from app.user import user_bp
from app.upload import upload_bp
from app.messages import messages_bp
from app.api import api_bp as api_v2_bp

#register blueprints
app.register_blueprint(error_bp)
app.register_blueprint(api_bp)
app.register_blueprint(qgen_bp)
app.register_blueprint(user_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(messages_bp)
app.register_blueprint(api_v2_bp)

#values every page template can use
from flask_wtf.csrf import generate_csrf
from datetime import datetime
from app.qgen.models import CQuiz, Setting, attempts_by_quiz

@app.context_processor
def page_helpers():
    def review_count():
        return CQuiz.query.filter_by(needs_review=True, completed=False).count()
    def site():
        try:
            return {'name': Setting.get('site_name', 'Quizzes'), 'logo': Setting.get('logo')}
        except Exception:
            #e.g. before the database is upgraded
            db.session.rollback()
            return {'name': 'Quizzes', 'logo': None}
    def asset(filename):
        """A stylesheet's or script's address stamped with when the file last changed,
        so browsers fetch the new copy after an update instead of a saved old one."""
        import os
        from flask import url_for
        try:
            version = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
        except OSError:
            version = 0
        return url_for('static', filename=filename, v=version)
    def unread_messages():
        from app.messages.models import unread_for_student, unread_for_teachers
        from flask_login import current_user
        if not current_user.is_authenticated:
            return 0
        return unread_for_teachers(current_user.id) if current_user.is_admin else unread_for_student(current_user.id)
    def unread_notices():
        from app.messages.models import unread_notices_for_student, unread_notices_for_teachers
        from flask_login import current_user
        if not current_user.is_authenticated:
            return 0
        return unread_notices_for_teachers(current_user.id) if current_user.is_admin else unread_notices_for_student(current_user.id)
    from app.user.avatars import initials, color
    return dict(csrf_token=generate_csrf, review_count=review_count, now=datetime.now,
                attempts_by_quiz=attempts_by_quiz, site=site, asset=asset, unread_messages=unread_messages, unread_notices=unread_notices,
                avatar_initials=initials, avatar_color=color)

#quizzes whose time is up are handed in and scored even if the student never
#returns: checked at most once a minute per server process
import time as _time
_last_sweep = [0.0]

@app.before_request
def _close_expired_quizzes():
    if _time.monotonic() - _last_sweep[0] < 60 or app.config.get('TESTING'):
        return
    _last_sweep[0] = _time.monotonic()
    from app.qgen.services import close_expired
    try:
        close_expired()
    except Exception as exc:  # never let the sweep break a page
        db.session.rollback()
        app.logger.error('closing expired quizzes failed: {}'.format(exc))

@app.cli.command('close-expired')
def close_expired_command():
    """Hand in and score every quiz whose time is up (for cron)."""
    from app.qgen.services import close_expired
    print('closed {} quiz attempt(s)'.format(close_expired()))

@app.cli.command('remove-old-markup')
@click.option('--yes', is_flag=True, help='Really delete (without it, only lists what would go).')
def remove_old_markup_command(yes):
    """Delete for good every problem in the old {{...}} markup, every quiz using one, and
    every student attempt at those (not archived). Back up the database first."""
    from app.qgen.services import old_markup_cleanup
    found = old_markup_cleanup(apply=yes)
    print('Problems ({}):'.format(len(found['problems'])))
    for pid, title in found['problems']:
        print('  {}  {}'.format(pid, title))
    print('Quizzes ({}):'.format(len(found['quizzes'])))
    for qid, title in found['quizzes']:
        print('  {}  {}'.format(qid, title))
    print('Student attempts ({}):'.format(len(found['attempts'])))
    for cid, qid, student in found['attempts']:
        print('  {}  quiz {}  student {}'.format(cid, qid, student))
    print('Deleted.' if yes else 'Nothing deleted. Run again with --yes to delete these for good.')

@app.cli.command('init-db')
def init_db_command():
    """Set up an empty database: create every table and mark it as up to date.
    (Existing databases are upgraded with `flask db upgrade` instead.)"""
    from flask_migrate import stamp
    from sqlalchemy import inspect
    import app.api.models, app.messages.models, app.qgen.models, app.user.models  # noqa: F401 (every table)
    if inspect(db.engine).get_table_names():
        print('This database already has tables; use "flask db upgrade" to bring it up to date.')
        return
    db.create_all()
    stamp()
    print('Database ready. Next: flask create-admin')

@app.cli.command('create-admin')
@click.argument('username')
def create_admin_command(username):
    """Create an administrator (asks for the password), e.g. for the very first login."""
    from app.user.models import User
    if User.query.filter_by(username=username).first():
        print('"{}" already exists.'.format(username))
        return
    from app.user.forms import MIN_PASSWORD
    password = click.prompt('Password', hide_input=True, confirmation_prompt=True)
    if len(password) < MIN_PASSWORD:
        print('Please use at least {} characters.'.format(MIN_PASSWORD))
        return
    u = User(username=username, is_admin=True)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    print('Administrator "{}" created. Log in, then set a class code under Settings.'.format(username))

@app.cli.command('set-password')
@click.argument('username')
def set_password_command(username):
    """Set a new password for an account (asks for it privately), e.g. a forgotten one."""
    from app.user.models import User
    from app.user.forms import MIN_PASSWORD
    u = User.query.filter_by(username=username).first()
    if not u:
        print('No account called "{}".'.format(username))
        return
    password = click.prompt('New password', hide_input=True, confirmation_prompt=True)
    if len(password) < MIN_PASSWORD:
        print('Please use at least {} characters.'.format(MIN_PASSWORD))
        return
    u.set_password(password)
    u.pw_man_reset = False
    db.session.commit()
    print('Password changed for "{}".'.format(username))

#create CLI command for DB dump
from app.commands import dbdump as dbdump_cli_group
app.cli.add_command(dbdump_cli_group, name='dbdump')

