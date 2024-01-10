from flask import render_template, flash
from app.error import error_bp
from app import db

@error_bp.app_errorhandler(404)
def notfound(error):
    flash(error)
    return render_template('404.html'), 404

@error_bp.app_errorhandler(500)
def interr(error):
    flash(error)
    db.session.rollback()
    return render_template('500.html'), 500

from app.error import handlers
