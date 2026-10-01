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
@upload_bp.route('/upload', methods=['POST','GET'])
@login_required
@pw_check
@admin_only
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        ufile = request.files['thefile']
        #need to generalize this
        path = static_dir()
        fname = secure_filename(ufile.filename)
        fpath = path + fname
        ufile.save(fpath)
        flash('{} saved'.format(ufile.filename))
        trythumb(path, fname)
        return redirect(url_for('upload.upload'))
    return render_template('upload.html', title='Upload a File', form=form)

#admin-only list images on server
@upload_bp.route('/images', methods=['GET'])
@login_required
@pw_check
@admin_only
def images():
    imgs = [(f,f[2:]) for f in static_files() if f.startswith('T_')]
    return render_template('images.html', imgs=imgs, title='Images')

#admin-only list non-image files on server
@upload_bp.route('/nonimages', methods=['GET'])
@login_required
@pw_check
@admin_only
def nonimages():
    allf = static_files()
    timgs = [f for f in allf if f.startswith('T_')]
    imgs = [f[2:] for f in timgs]
    imgs += timgs
    nonims = [f for f in allf if f not in imgs]
    return render_template('nonimages.html', files=nonims, title='Non-Image Files')

#admin-only delete an image from server
@upload_bp.route('/delimg/<fname>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delimg(fname):
    if fname not in static_files():
        flash('Image not found: {}'.format(fname))
    else:
        try:
            remove(static_dir() + fname)
            remove(static_dir() + 'T_' + fname)
            flash('Image and thumbnail removed: {}'.format(fname))
            current_app.logger.info('{} removed image and thumbnail for {}'.format(current_user.username, fname))
        except Exception as exc:
            flash('Deletion failed for {}'.format(fname))
    return redirect(url_for('upload.images'))

#admin-only delete a non-image from server
@upload_bp.route('/delnonimg/<fname>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delnonimg(fname):
    if fname not in static_files():
        flash('File not found: {}'.format(fname))
    else:
        try:
            remove(static_dir() + fname)
            flash('File removed: {}'.format(fname))
            current_app.logger.info('{} removed file {}'.format(current_user.username, fname))
        except Exception as exc:
            flash('Deletion failed for {}'.format(fname))
    return redirect(url_for('upload.nonimages'))



#pick a free file name so a new upload never replaces an existing one
def unique_name(fname):
    base, dot, ext = fname.rpartition('.')
    if not dot:
        base, ext = fname, ''
    existing = set(listdir(static_dir()))
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
    #only real pictures, checked by opening them
    try:
        im = Image.open(ufile.stream)
        im.verify()
    except Exception:
        return jsonify(ok=False, error='That doesn\'t look like a picture.'), 400
    ufile.stream.seek(0)
    fname = unique_name(fname)
    ufile.save(static_dir() + fname)
    trythumb(static_dir(), fname, quiet=True)
    current_app.logger.info('{} uploaded {}'.format(current_user.username, fname))
    return jsonify(ok=True, name=fname, url=url_for('static', filename=fname))

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
