"""Deleting an account (Users page's Delete, and taking someone out of their last folder)."""
from app import db


def delete_account(usr, by):
    """Delete someone's account: their quiz attempts go to the Archive first, then their
    picture, then the account; a teacher's unfinished scans go to `by`, the teacher deleting it.
    Returns their username."""
    from . import avatars
    from app.qgen import services as S
    from app.qgen.scan import hand_over_jobs
    from .models import User
    name = usr.username
    S.archive_student(usr, by=by)
    #(its Archive folder becomes “ava (deleted)”: a new “ava” gets a folder of her own)
    S.mark_deleted_folder(usr)
    avatars.remove(usr, commit=False)
    hand_over_jobs(usr, by)  # their unfinished workbook scans
    User.query.filter_by(id=usr.id).delete()
    db.session.commit()
    return name


def archive_account(usr, by, keep_results=True):
    """The trash can's Move to Archive for a person (the owner, 2026-10-16): they can't log in and
    are left out of every list of people (app/user/models.py); they stay in their folders. keep_results False: their quiz attempts, and their attempts in the
    Archive, are deleted for good first."""
    import json
    from datetime import datetime
    from app.qgen import services as S
    from app.qgen.models import CQuiz, ArchivedAttempt
    from .models import UserFolderMember
    if not keep_results:
        for cq in CQuiz.query.filter_by(assignee=usr.id).all():
            S._erase_attempt(cq)
        ArchivedAttempt.query.filter_by(student_id=usr.id).delete()
    #(they stay in their folders: the Archive's People shows them there; left out elsewhere)
    usr.archived_at = datetime.now()
    usr.logged_in = False
    db.session.commit()


def restore_account(usr):
    """An archived person back: they can log in again, in Uncategorized (out of the folders they
    were in: the owner, 2026-10-16)."""
    from .models import UserFolderMember
    UserFolderMember.query.filter_by(user_id=usr.id).delete()
    usr.archived_at, usr.archived_folders = None, None
    db.session.commit()


def archived_people():
    from .models import User
    return (User.query.filter(User.archived_at.isnot(None)).execution_options(include_archived=True)
            .order_by(User.archived_at.desc()).all())


def any_person(uid):
    """Someone by id, archived or not (the Archive's Restore and Delete for good)."""
    from .models import User
    return User.query.filter_by(id=uid).execution_options(include_archived=True).first()
