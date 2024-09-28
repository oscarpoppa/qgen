from . import upload_bp
from .forms import UploadForm
from app.user.routes import admin_only, pw_check
from flask import flash, render_template, redirect, url_for, request, current_app
from flask_login import current_user, login_user, login_required, logout_user
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from PIL import Image
from os import listdir, remove

STATIC = '/home/dan/proj/quiz/app/static/'

#try to create a thumbnail
def trythumb(path, fname):
    fpath = path + fname
    try:
        im = Image.open(fpath)    
        im.thumbnail((128, 128))
        tname = 'T_' + fname
        nupath = path + tname
        im.save(nupath)
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
        path = STATIC
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
    imgs = [(f,f[2:]) for f in listdir(STATIC) if f.startswith('T_')]
    return render_template('images.html', imgs=imgs, title='Images')

#admin-only list non-image files on server
@upload_bp.route('/nonimages', methods=['GET'])
@login_required
@pw_check
@admin_only
def nonimages():
    allf = listdir(STATIC)
    timgs = [f for f in allf if f.startswith('T_')]
    imgs = [f[2:] for f in timgs]
    imgs += timgs
    nonims = [f for f in allf if f not in imgs]
    return render_template('nonimages.html', files=nonims, title='Non-Image Files')

#admin-only delete an image from server
@upload_bp.route('/delimg/<fname>', methods=['GET'])
@login_required
@pw_check
@admin_only
def delimg(fname):
    if fname not in [f for f in listdir(STATIC)]:
        flash('Image not found: {}'.format(fname))
    else:
        try:
            remove(STATIC + fname)
            remove(STATIC + 'T_' + fname)
            flash('Image and thumbnail removed: {}'.format(fname))
            current_app.logger.info('{} removed image and thumbnail for {}'.format(current_user.username, fname))
        except Exception as exc:
            flash('Deletion failed for {}'.format(fname))
    return redirect(url_for('upload.images'))

#admin-only delete a non-image from server
@upload_bp.route('/delnonimg/<fname>', methods=['GET'])
@login_required
@pw_check
@admin_only
def delnonimg(fname):
    if fname not in [f for f in listdir(STATIC)]:
        flash('File not found: {}'.format(fname))
    else:
        try:
            remove(STATIC + fname)
            flash('File removed: {}'.format(fname))
            current_app.logger.info('{} removed file {}'.format(current_user.username, fname))
        except Exception as exc:
            flash('Deletion failed for {}'.format(fname))
    return redirect(url_for('upload.nonimages'))

