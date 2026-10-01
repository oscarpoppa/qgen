"""Signing requests with a personal access token."""
from datetime import datetime, timedelta
from functools import wraps

from flask import g, request

from app import db
from .errors import ApiError
from .models import ApiToken

#last_used is written at most this often, not on every request
TOUCH_EVERY = timedelta(minutes=1)


def current_token():
    header = request.headers.get('Authorization', '')
    scheme, _, token = header.partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        raise ApiError(401, 'unauthorized', 'Sign in first: send "Authorization: Bearer <token>". '
                       'Get a token from POST /api/v2/tokens.')
    row = ApiToken.find(token.strip())
    if not row:
        raise ApiError(401, 'unauthorized', 'That token isn\'t valid: it may be mistyped, expired or revoked.')
    return row


def token_required(teacher=False):
    """Decorator: sets g.api_user and g.api_token. teacher=True also requires an administrator."""
    def wrap(view):
        @wraps(view)
        def inner(*args, **kwargs):
            row = current_token()
            user = row.user
            if user.pw_man_reset:
                raise ApiError(403, 'password_change_required',
                               'This account\'s password was reset. Change it on the website first.')
            if teacher and not user.is_admin:
                raise ApiError(403, 'forbidden', 'Only teachers can do that.')
            now = datetime.now()
            if not row.last_used or now - row.last_used > TOUCH_EVERY:
                row.last_used = now
                db.session.commit()
            g.api_user, g.api_token = user, row
            return view(*args, **kwargs)
        return inner
    return wrap


def body(required=()):
    """The request's JSON object; 400 if it's missing, not an object, or lacks required keys."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, 'bad_request', 'Send a JSON object in the request body (Content-Type: application/json).')
    missing = [k for k in required if k not in data]
    if missing:
        raise ApiError(400, 'bad_request', 'Missing: {}.'.format(', '.join(missing)), {'missing': missing})
    return data
