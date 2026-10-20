"""Uploaded pictures and other files as rows (UploadFile), so they can be put in folders like
problems and quizzes (the owner, 2026-10-19). The static folder is still the truth: sync() adds
a row for each file there and drops the rows of files that are gone. A picture is a file with a
thumbnail (T_<name>), as the Pictures page has always told them apart."""
from datetime import datetime
from os import remove
from os.path import getmtime
from flask import current_app

from app import db
from .models import UploadFile


NAME_MAX = 191  # (the column's length: a unique index on MySQL utf8mb4 fits 191 characters)


def sync():
    """Rows for every uploaded file, none for files that are gone. Cheap when nothing changed.
    Call it where files change (upload, delete, a scan's pictures) and when the Pictures / Other
    files pages open; it commits. Two pages syncing at once (every teacher's page is told to reload
    after an upload) can both add the same new file: the second one's insert is then simply
    dropped (the owner, 2026-10-19, from the code critic)."""
    from sqlalchemy.exc import IntegrityError
    from app.upload.routes import static_files, static_dir
    files = static_files()
    thumbs = {f[2:] for f in files if f.startswith('T_')}
    real = {f: f in thumbs for f in files if not f.startswith('T_') and len(f) <= NAME_MAX}
    rows = {u.name: u for u in UploadFile.query.all()}
    for name, picture in real.items():
        u = rows.get(name)
        if u is None:
            #(made when the file was: its own date, for the Created column)
            try:
                made = datetime.fromtimestamp(getmtime(static_dir() + name))
            except OSError:
                made = datetime.now()
            try:
                with db.session.begin_nested():
                    db.session.add(UploadFile(name=name, picture=picture, create_date=made))
            except IntegrityError:
                pass  # (another page added it a moment ago)
        elif u.picture != picture:
            u.picture = picture
    for name, u in rows.items():
        if name not in real:
            db.session.delete(u)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()


def get(name):
    """The row for an uploaded file, made if it's there and has none yet."""
    u = UploadFile.query.filter_by(name=name).first()
    if u is None:
        sync()
        u = UploadFile.query.filter_by(name=name).first()
    return u


def delete_file(u):
    """Delete an upload for good: the file, its thumbnail, and its row (and so its folders)."""
    from app.upload.routes import static_dir, files_changed
    for f in (u.name, 'T_' + u.name):
        try:
            remove(static_dir() + f)
        except FileNotFoundError:
            pass
    db.session.delete(u)
    db.session.commit()
    files_changed()
    current_app.logger.info('deleted upload {}'.format(u.name))


def file_in_folder(name, folder_title, kind='pictures'):
    """Put an upload in the folder of that name (made if there isn't one): a scan's pictures go in
    the workbook's folder. Returns the folder, or None when the file isn't there."""
    from . import services as S
    u = get(name)
    if u is None:
        return None
    g = S.subject_named(kind, folder_title)
    S.file_one(kind, u.id, g)
    return g
