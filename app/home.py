"""Where someone's "home" is: administrators land on the Dashboard, students on Home."""
from flask import url_for
from flask_login import current_user


def home_url(user=None):
    user = user if user is not None else current_user
    if getattr(user, 'is_authenticated', False) and user.is_admin:
        return url_for('qgen.dashboard')
    return url_for('user.home')
