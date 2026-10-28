from . import upload_bp
from app.jsoncsrf import post_form_only
from .forms import UploadForm
from app.user.routes import admin_only, pw_check
from flask import flash, render_template, redirect, url_for, request, current_app, jsonify, abort
from app.jsoncsrf import json_csrf_ok
from flask_login import current_user, login_user, login_required, logout_user
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from PIL import Image
from os import listdir, remove, path as osp


def files_changed():
    """Uploads aren't in the database, so saving one tells no one by itself: tell the
    teachers' open pages (Pictures, Other files) to check now. Their rows (for folders) are
    brought up to date first, here, where the files changed."""
    try:
        from app.qgen import uploads
        uploads.sync()
    except Exception as exc:
        current_app.logger.warning('upload rows not synced: {}'.format(exc))
    from app.push import tell, TEACHERS
    tell({TEACHERS})

#uploads live in the configured static folder (css/ and js/ subfolders are site assets)
def static_dir():
    return osp.join(current_app.config['STATIC_DIR'], '')

def static_files():
    sdir = static_dir()
    return [f for f in listdir(sdir) if osp.isfile(sdir + f)]

#try to create a thumbnail
def trythumb(path, fname, quiet=False):
    fpath = path + fname
    try:
        im = Image.open(fpath)    
        im.thumbnail((128, 128))
        tname = 'T_' + fname
        nupath = path + tname
        im.save(nupath)
        if not quiet:
            flash('Created thumbnail {}'.format(tname))
    except Exception as exc:
        pass

#admin-only upload image or file to server
#(files a browser runs as part of the site when opened from it: never uploaded, the owner
#2026-10-20 from the code critic: an uploaded page or drawing could run code with a teacher's sign-in)
BLOCKED = ('html', 'htm', 'xhtml', 'shtml', 'mhtml', 'mht', 'svg', 'svgz', 'js', 'mjs', 'xml', 'xsl')  # (more, the code critic 2026-10-22)
BLOCKED_SAY = 'That kind of file can’t be uploaded: it could run code on the site.'


def blocked(fname):
    return fname.rpartition('.')[2].lower() in BLOCKED if '.' in fname else False


@upload_bp.route('/upload', methods=['POST','GET'])
@login_required
@pw_check
@admin_only
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        ufile = request.files['thefile']
        path = static_dir()
        fname = secure_filename(ufile.filename)
        if not fname:
            flash('That file name can\'t be used. Rename the file and try again.', 'error')
            return redirect(url_for('upload.upload'))
        if blocked(fname):
            flash(BLOCKED_SAY, 'error')
            return redirect(url_for('upload.upload'))
        #never over a file already there (a picture problems use, its thumbnail, or a site folder)
        saved = unique_name(fname)
        ufile.save(path + saved)
        trythumb(path, saved, quiet=True)
        files_changed()
        if saved == fname:
            flash('Uploaded “{}”.'.format(saved), 'success')
        else:
            flash('Uploaded “{}” as “{}”, since a file called “{}” is already there.'.format(fname, saved, fname), 'success')
        current_app.logger.info('{} uploaded {}'.format(current_user.username, saved))
        return redirect(url_for('upload.upload'))
    return render_template('upload.html', title='Upload Files', form=form)

#admin-only list images on server
@upload_bp.route('/images', methods=['GET'])
@login_required
@pw_check
@admin_only
def images():
    #A to Z by name, whatever case (the owner, 2026-10-17), in folders like Problems (2026-10-19)
    from app.qgen.routes import subject_page
    from app.qgen import services as S, uploads
    uploads.sync()
    return subject_page('pictures', 'images.html', title='Pictures', all_subjects=S.subject_tree('pictures')[1],
                        file_blocker=S.file_delete_blocker)

#admin-only list non-image files on server
@upload_bp.route('/nonimages', methods=['GET'])
@login_required
@pw_check
@admin_only
def nonimages():
    #A to Z by name, whatever case, like Pictures (the owner, 2026-10-17), in folders (2026-10-19)
    from app.qgen.routes import subject_page
    from app.qgen import services as S, uploads
    uploads.sync()
    return subject_page('files', 'nonimages.html', title='Other files', all_subjects=S.subject_tree('files')[1],
                        file_blocker=S.file_delete_blocker)

#admin-only delete an image from server
@upload_bp.route('/delimg/<fname>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delimg(fname):
    from app.qgen import services as S
    #(not while a problem or quiz uses it: its Delete is grayed with this too; the owner, 2026-10-26)
    why = S.file_delete_blocker(fname, 'pictures')
    if fname not in static_files():
        flash('Couldn’t find the picture “{}”. It may have been deleted already.'.format(fname), 'error')
    elif why:
        flash(why, 'error')
    else:
        try:
            remove(static_dir() + fname)
            remove(static_dir() + 'T_' + fname)
            files_changed()
            flash('Deleted “{}”.'.format(fname), 'success')
            current_app.logger.info('{} removed image and thumbnail for {}'.format(current_user.username, fname))
        except Exception as exc:
            flash('Couldn’t delete “{}”. Please try again.'.format(fname), 'error')
    return back_to_list('upload.images')

#admin-only delete a non-image from server
@upload_bp.route('/delnonimg/<fname>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delnonimg(fname):
    from app.qgen import services as S
    why = S.file_delete_blocker(fname, 'files')
    if fname not in static_files():
        flash('Couldn’t find the file “{}”. It may have been deleted already.'.format(fname), 'error')
    elif why:
        flash(why, 'error')
    else:
        try:
            remove(static_dir() + fname)
            files_changed()
            flash('Deleted “{}”.'.format(fname), 'success')
            current_app.logger.info('{} removed file {}'.format(current_user.username, fname))
        except Exception as exc:
            flash('Couldn’t delete “{}”. Please try again.'.format(fname), 'error')
    return back_to_list('upload.nonimages')



#a picture's or other file's trash can: Move to Trash, and the Trash's Restore and Delete for good (the owner, 2026-10-26,
#To do 66; they were only ever deleted for good). Not while a problem or quiz uses it, like a problem's.
def _upload_or_gone(uid):
    from app.qgen.models import UploadFile
    from app import db
    u = db.session.get(UploadFile, uid)
    if u is None:
        flash('That file has been deleted.', 'info')
    return u


def _kind(u):
    return 'pictures' if u.picture else 'files'


@upload_bp.route('/upload/<int:uid>/trash', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def trash_upload(uid):
    from markupsafe import Markup
    from app.qgen import services as S, uploads
    u = _upload_or_gone(uid)
    if u is None or u.removed_at:
        return back_to_list('upload.images' if u is None or u.picture else 'upload.nonimages')
    page = 'upload.images' if u.picture else 'upload.nonimages'
    why = S.file_delete_blocker(u.name, _kind(u))
    if why:
        flash(why, 'error')
        return back_to_list(page)
    try:
        uploads.trash_file(u)
    except OSError:
        current_app.logger.exception('could not move {} to the Trash'.format(u.name))
        flash('Couldn’t move “{}” to the Trash. Please try again.'.format(u.name), 'error')
        return back_to_list(page)
    flash(Markup('Moved “{}” to the <a href="{}">Trash</a>, where you can restore it.').format(
        u.name, url_for('qgen.archive', section=_kind(u))), 'success')
    return back_to_list(page)


@upload_bp.route('/upload/<int:uid>/restore', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def restore_upload(uid):
    from app.qgen import uploads
    u = _upload_or_gone(uid)
    if u is not None and u.removed_at:
        try:
            uploads.restore_file(u)
        except OSError:
            current_app.logger.exception('could not restore {}'.format(u.name))
            flash('Couldn’t restore “{}”. Please try again.'.format(u.name), 'error')
            return redirect(url_for('qgen.archive', section=_kind(u)))
        flash('“{}” is back on the {} page.'.format(u.name, 'Pictures' if u.picture else 'Other files'), 'success')
    return redirect(url_for('qgen.archive', section=_kind(u) if u is not None else 'pictures'))


@upload_bp.route('/upload/<int:uid>/delete', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delete_trashed_upload(uid):
    from app.qgen import uploads
    u = _upload_or_gone(uid)
    if u is not None and u.removed_at:
        from app.qgen import services as S
        name, kind = u.name, _kind(u)
        why = S.file_delete_blocker(name, kind)
        if why:
            flash(why, 'error')
            return redirect(url_for('qgen.archive', section=kind))
        uploads.delete_file(u)
        flash('Deleted “{}”.'.format(name), 'success')
        current_app.logger.info('{} deleted {} from the Trash for good'.format(current_user.username, name))
        return redirect(url_for('qgen.archive', section=kind))
    return redirect(url_for('qgen.archive', section='pictures'))


#a picture (or file) in the Trash, to see it there: teachers only, from the private trash folder
@upload_bp.route('/upload/trashed/<path:fname>', methods=['GET'])
@login_required
@pw_check
@admin_only
def trashed_file(fname):
    from flask import send_from_directory
    from app.qgen.uploads import trash_dir
    return send_from_directory(trash_dir(), fname)


def back_to_list(endpoint):
    """After a delete: back to the page as it was (the folder and tab open), else its start."""
    from urllib.parse import urlsplit
    ref = urlsplit(request.referrer or '')
    if ref.netloc == request.host and ref.path == url_for(endpoint):
        return redirect(ref.path + ('?' + ref.query if ref.query else ''))
    return redirect(url_for(endpoint))

#pick a free file name so a new upload never replaces an existing one
def unique_name(fname):
    base, dot, ext = fname.rpartition('.')
    if not dot:
        base, ext = fname, ''
    #(nor a name in the Trash, so a picture restored from there never meets a new one of its name: the owner, 2026-10-26)
    from app.qgen.uploads import trashed_names
    existing = set(listdir(static_dir())) | trashed_names()
    cand, n = fname, 1
    while cand in existing or 'T_' + cand in existing:
        n += 1
        cand = '{}-{}{}{}'.format(base, n, dot, ext)
    return cand

#admin-only drag-and-drop upload; returns JSON for static/js/dropzone.js
@upload_bp.route('/upload/json', methods=['POST'])
@login_required
@pw_check
@admin_only
def upload_json():
    if not json_csrf_ok():
        return jsonify(ok=False, error='Your session expired. Please reload the page.'), 400
    ufile = request.files.get('file')
    if not ufile or not ufile.filename:
        return jsonify(ok=False, error='No file received.'), 400
    fname = secure_filename(ufile.filename)
    if not fname:
        return jsonify(ok=False, error='That file name can\'t be used.'), 400
    if blocked(fname):
        return jsonify(ok=False, error=BLOCKED_SAY), 400
    #only real pictures, checked by opening them; with ?any=1 (Upload files' one drop box: the
    #owner, 2026-10-19) anything else is kept too, as an other file (no thumbnail)
    anyfile = request.args.get('any') == '1'
    try:
        im = Image.open(ufile.stream)
        im.verify()
        picture = True
    except Exception:
        if not anyfile:
            return jsonify(ok=False, error='That doesn\'t look like a picture.'), 400
        picture = False
    ufile.stream.seek(0)
    fname = unique_name(fname)
    ufile.save(static_dir() + fname)
    if picture:
        trythumb(static_dir(), fname, quiet=True)
    #(a dropped folder's pictures go in a Pictures folder of its name, made or reused: the owner,
    #2026-10-19)
    folder = ' '.join((request.form.get('folder') or '').split())[:60]
    if folder:
        from app.qgen.uploads import file_in_folder
        try:
            file_in_folder(fname, folder)
        except Exception:  # (a name that can't be a folder: the picture is still uploaded)
            from app import db
            db.session.rollback()
            current_app.logger.exception('could not file {} in folder {!r}'.format(fname, folder))
    files_changed()
    current_app.logger.info('{} uploaded {}'.format(current_user.username, fname))
    return jsonify(ok=True, name=fname, url=url_for('static', filename=fname), picture=picture,
                   thumb=url_for('static', filename='T_' + fname) if picture else None)

#admin-only list of uploaded pictures for the picker
@upload_bp.route('/upload/imagelist', methods=['GET'])
@login_required
@pw_check
@admin_only
def image_list():
    files = static_files()
    thumbs = {f[2:] for f in files if f.startswith('T_')}
    items = [dict(name=f, url=url_for('static', filename=f),
                  thumb=url_for('static', filename='T_' + f if f in thumbs else f))
             for f in sorted(files) if not f.startswith('T_') and (f in thumbs or is_image_name(f))]
    return jsonify(items)

def is_image_name(fname):
    return fname.rsplit('.', 1)[-1].lower() in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp')
