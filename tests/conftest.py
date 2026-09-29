import os
import sys

#tests never touch a real database or need a real .env
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('SECRET_KEY', 'test-only-secret')
#uploads during tests go to a throwaway folder
import tempfile
os.environ['STATIC_DIR'] = tempfile.mkdtemp(prefix='qgen-test-static-')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import pytest


@pytest.fixture(autouse=True)
def fresh_login_per_request():
    """Tests run many requests inside one app context, where Flask-Login caches
    the current user; clear it per request, as a real server effectively does."""
    from flask import g
    from app import app

    def clear():
        g.pop('_login_user', None)
    app.before_request_funcs.setdefault(None, []).insert(0, clear)
    yield
    app.before_request_funcs[None].remove(clear)
