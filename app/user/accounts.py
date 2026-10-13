"""Deleting an account (Users page's Delete, and taking someone out of their last folder)."""
from app import db


def delete_account(usr, by):
    """Delete someone's account: their quiz attempts go to the Archive first, then their
    picture and unfinished scans, then the account. Returns their username."""
    from . import avatars
    from app.qgen import services as S
    from app.qgen.scan import remove_user_jobs
    from .models import User
    name = usr.username
    S.archive_student(usr, by=by)
    avatars.remove(usr, commit=False)
    remove_user_jobs(usr)  # their unfinished workbook scans
    User.query.filter_by(id=usr.id).delete()
    db.session.commit()
    return name
