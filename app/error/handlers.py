from . import db, error_bp
from flask import render_template

#handler for 404 error
@error_bp.app_errorhandler(404)
def notfound(error):
    #(the page itself says what happened; no raw "404 Not Found: ..." message on top)
    return render_template('404.html', title='Page Not Found'), 404

#handler for 500 error
@error_bp.app_errorhandler(500)
def interr(error):
    db.session.rollback()
    return render_template('500.html', title='Something Went Wrong'), 500

from app.error import handlers
