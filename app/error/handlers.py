from . import db, error_bp
from flask import render_template, flash

#handler for 404 error
@error_bp.app_errorhandler(404)
def notfound(error):
    flash(error)
    return render_template('404.html', title='Page not found'), 404

#handler for 500 error
@error_bp.app_errorhandler(500)
def interr(error):
    flash(error)
    db.session.rollback()
    return render_template('500.html', title='Something went wrong'), 500

from app.error import handlers
