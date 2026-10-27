import os
import sys

#tests never touch a real database or need a real .env. Always set, never
#"if not set": the tests empty the database they use, so a DATABASE_URL left in
#the shell (e.g. the live or sandbox one) must not be picked up
#(a throwaway file, not one in memory: a database in memory is a single connection that every thread shares,
#and the scan pages read side by side then tripped over each other's queries; 2026-10-25)
import tempfile
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(tempfile.mkdtemp(prefix='qgen-test-db-'), 'test.db')
os.environ['SECRET_KEY'] = 'test-only-secret'
#uploads during tests go to a throwaway folder
os.environ['STATIC_DIR'] = tempfile.mkdtemp(prefix='qgen-test-static-')
os.environ['SCAN_DIR'] = tempfile.mkdtemp(prefix='qgen-test-scans-')
os.environ['UPLOAD_TRASH_DIR'] = tempfile.mkdtemp(prefix='qgen-test-upload-trash-')
os.environ['AI_JOB_DIR'] = tempfile.mkdtemp(prefix='qgen-test-ai-jobs-')
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
