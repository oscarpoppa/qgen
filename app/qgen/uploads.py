"""Uploaded pictures and other files as rows (UploadFile), so they can be put in folders like
problems and quizzes (the owner, 2026-10-19). The static folder is still the truth: sync() adds
a row for each file there and drops the rows of files that are gone. A picture is a file with a
thumbnail (T_<name>), as the Pictures page has always told them apart."""
import os
from datetime import datetime
from os import remove
from os.path import getmtime
from flask import current_app

from app import db
from .models import UploadFile


NAME_MAX = 191  # (the column's length: a unique index on MySQL utf8mb4 fits 191 characters)


_last_sync = None   # (the folder's change time and the row count, at the last full sync)


def sync():
    """Rows for every uploaded file, none for files that are gone. Cheap when nothing changed.
    Call it where files change (upload, delete, a scan's pictures) and when the Pictures / Other
    files pages open; it commits. Two pages syncing at once (every teacher's page is told to reload
    after an upload) can both add the same new file: the second one's insert is then simply
    dropped (the owner, 2026-10-19, from the code critic)."""
    from sqlalchemy.exc import IntegrityError
    from app.upload.routes import static_files, static_dir, trythumb, is_image_name
    #(nothing to do when the folder and the rows are as they were at the last sync: forms with a
    #picture picker call this on every visit; the code critic, 2026-10-20)
    global _last_sync
    try:
        key = (os.stat(static_dir()).st_mtime_ns, UploadFile.query.count())
    except OSError:
        key = None
    if key is not None and key == _last_sync:
        return
    files = static_files()
    thumbs = {f[2:] for f in files if f.startswith('T_')}
    #a picture put there without one (copied in, not uploaded) gets its thumbnail now, so it's
    #on Pictures, not Other files (the owner, 2026-10-19); one that won't open stays an other file
    missing = [f for f in files if not f.startswith('T_') and f not in thumbs and is_image_name(f)]
    for f in missing:
        trythumb(static_dir(), f, quiet=True)
    if missing:
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
        if name not in real and u.removed_at is None:  # (one in the Trash has its file there: kept)
            db.session.delete(u)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return
    try:
        _last_sync = (os.stat(static_dir()).st_mtime_ns, UploadFile.query.count())
    except OSError:
        _last_sync = None


def get(name):
    """The row for an uploaded file, made if it's there and has none yet."""
    u = UploadFile.query.filter_by(name=name).first()
    if u is None:
        sync()
        u = UploadFile.query.filter_by(name=name).first()
    return u


def trash_dir():
    """Where pictures and other files in the Trash are kept (private: not under static)."""
    d = current_app.config['UPLOAD_TRASH_DIR']
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, '')


def trashed_names():
    try:
        return set(os.listdir(trash_dir()))
    except OSError:
        return set()


def _move(names, src, dst):
    for f in names:
        try:
            os.replace(src + f, dst + f)
        except FileNotFoundError:
            pass  # (a picture's thumbnail may be missing)


def trash_file(u):
    """Move to Trash for a picture or other file (the owner, 2026-10-26, To do 66): its file and thumbnail go to the
    private trash folder, off Pictures / Other files and every picture picker; it stays in its folders, like a problem."""
    from app.upload.routes import static_dir, files_changed
    _move((u.name, 'T_' + u.name), static_dir(), trash_dir())
    u.removed_at = datetime.now()
    db.session.commit()
    files_changed()
    current_app.logger.info('moved upload {} to the Trash'.format(u.name))


def restore_file(u):
    """Back from the Trash, in Uncategorized (out of the folders it was in, like a restored problem). Its name can't
    have been taken meanwhile: a new upload's name is never one in the Trash (upload/routes.py unique_name)."""
    from app.upload.routes import static_dir, files_changed
    _move((u.name, 'T_' + u.name), trash_dir(), static_dir())
    u.removed_at = None
    u.picgroups, u.filegroups = [], []
    db.session.commit()
    files_changed()
    current_app.logger.info('restored upload {}'.format(u.name))


def removed(kind):
    """The pictures (or other files) in the Trash."""
    return UploadFile.query.filter(UploadFile.removed_at.isnot(None), UploadFile.picture.is_(kind == 'pictures')).all()


def delete_file(u):
    """Delete an upload for good: the file, its thumbnail, and its row (and so its folders); from the Trash too."""
    from app.upload.routes import static_dir, files_changed
    where = trash_dir() if u.removed_at else static_dir()
    for f in (u.name, 'T_' + u.name):
        try:
            remove(where + f)
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
