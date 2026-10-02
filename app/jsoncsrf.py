"""CSRF check for the JSON endpoints called by page scripts.
The page puts the token in <meta name="csrf-token">; scripts send it as X-CSRFToken."""
from flask import current_app, request
from flask_wtf.csrf import validate_csrf
from wtforms.validators import ValidationError


def json_csrf_ok():
    if not current_app.config.get('WTF_CSRF_ENABLED', True):
        return True
    try:
        validate_csrf(request.headers.get('X-CSRFToken'))
        return True
    except ValidationError:
        return False


def form_csrf_ok():
    """The same check for plain HTML forms that post csrf_token without a FlaskForm."""
    if not current_app.config.get('WTF_CSRF_ENABLED', True):
        return True
    try:
        validate_csrf(request.form.get('csrf_token'))
        return True
    except ValidationError:
        return False


def post_form_only(view):
    """For actions that change things (delete, retake, release, reset password):
    only a POSTed form with this site's session token may trigger them, so another
    website can't make a signed-in teacher's browser do it (cross-site request forgery)."""
    from functools import wraps
    from flask import flash, redirect, url_for
    from app.home import home_url

    @wraps(view)
    def inner(*args, **kwargs):
        if request.method != 'POST' or not form_csrf_ok():
            flash('That didn\'t go through (the page was out of date). Please try again.', 'error')
            return redirect(request.referrer or home_url())
        return view(*args, **kwargs)
    return inner
