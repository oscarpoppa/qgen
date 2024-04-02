from . import user_bp
from app import app, db
from .models import User
from .forms import RegistrationForm, LoginForm, UploadForm, ChPassForm
from flask import flash, render_template, redirect, url_for, request, current_app
from flask_login import current_user, login_user, login_required, logout_user
from flask_wtf import FlaskForm
from wtforms_sqlalchemy.orm import model_form
from werkzeug.utils import secure_filename
from functools import wraps
from PIL import Image
from os import listdir, remove

STATIC = '/home/dan/proj/quiz/app/static/'

# Decorator to kick user back to mypage if already logged in
def logout_required(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if current_user.is_authenticated:
            flash('{} is unavailable while logged in'.format(request.__dict__['environ']['RAW_URI']))
            return redirect(url_for('user.mypage'))
        return func(*args, **kwargs)
    return inner

# Decorator to kick user back to mypage if not admin
def admin_only(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if not current_user.is_admin:
            flash('{} is available to administrators only'.format(request.__dict__['environ']['RAW_URI']))
            return redirect(url_for('user.mypage'))
        return func(*args, **kwargs)
    return inner

# Decorator to kick user back to password change after manual reset
def pw_check(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if current_user.pw_man_reset:
            flash('Please change your password before continuing')
            return redirect(url_for('user.chpass'))
        else:
            return func(*args, **kwargs)
    return inner

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

@user_bp.route('/mypage')
@login_required
@pw_check
def mypage():
    return render_template('mypage.html', current_user=current_user, title='{}\'s Page'.format(current_user.username))

@user_bp.route('/logout')
@login_required
@pw_check
def logout():
    flash('{} has been logged out'.format(current_user.username))
    current_app.logger.info('{} has logged out'.format(current_user.username))
    current_user.logged_in = False
    current_user.save()
    logout_user()
    return redirect(url_for('user.login'))

@user_bp.route('/upload', methods=['POST','GET'])
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
        return redirect(url_for('user.upload'))
    return render_template('upload.html', title='Upload a File', form=form)

@user_bp.route('/', methods=['POST','GET'])
@user_bp.route('/login', methods=['POST','GET'])
@logout_required
def login():
    form = LoginForm()
    if form.validate_on_submit():
        u = User.query.filter_by(username=form.username.data).first()
        if u is None or not u.check_password(form.password.data):
            flash('Invalid Username/Password')
            return redirect(url_for('user.login')) 
        login_user(u, remember=True)
        u.logged_in = True
        u.save()
        current_app.logger.info('{} has logged in'.format(u.username))
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('user.mypage'))
    return render_template('login.html', title='Login Now!', form=form)

@user_bp.route('/register', methods=['POST','GET'])
@logout_required
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        u = User(username=form.username.data, email=form.email.data)
        u.set_password(form.password.data)
        u.save()
        current_app.logger.info('User {} has been created'.format(u.username))
        flash('Account {} registered'.format(form.username.data))
        return redirect(url_for('user.login'))
    else:
        return render_template('register.html', title='Register Now!', form=form)

@user_bp.route('/chpass', methods=['POST','GET'])
@login_required
def chpass():
    form = ChPassForm()
    user = current_user
    if form.validate_on_submit():
        if not user.check_password(form.old_password.data):
            flash('Old Password Error')
            return redirect(url_for('user.chpass'))
        user.set_password(form.password.data)
        user.pw_man_reset = False
        user.save()
        flash('Password changed')
        return redirect(url_for('user.mypage'))
    return render_template('chpass.html', title='Changing Password for {}'.format(user.username), form=form)

@user_bp.route('/resetpass/<uid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def resetpass(uid):
    usrquery = User.query.filter_by(id=uid)
    usr = usrquery.first_or_404('No user with id {}'.format(uid))
    pword = 'PASSWORD'
    usr.set_password(pword)
    usr.pw_man_reset = True
    usr.save()
    flash('Password reset for {}'.format(usr.username))
    current_app.logger.info('{} issued a manual PW reset for {}:{}'.format(current_user.username, usr.username, pword))
    return redirect(url_for('user.userdet'))

@user_bp.route('/deluser/<uid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def deluser(uid):
    usrquery = User.query.filter_by(id=uid)
    usr = usrquery.first_or_404('No user with id {}'.format(uid))
    usrname = usr.username
    if current_user == usr:
        flash("I can't let you do that, {}".format(current_user.username))
        return redirect(url_for('user.userdet'))
    usrquery.delete()
    db.session.commit()
    current_app.logger.info('User {} has been deleted'.format(usrname))
    flash('{} deleted user: {}'.format(current_user.username, usrname))
    return redirect(url_for('user.userdet'))

@user_bp.route('/edituser/<uid>', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def eduser(uid):
    uform = model_form(User, base_class=FlaskForm, db_session=db)
    uobj = User.query.filter_by(id=uid).first_or_404('No user with id {}'.format(uid))
    form = uform(obj=uobj)
    if request.method == 'POST':
        uobj.username = form.username.data
        uobj.email = form.email.data
        if uobj == current_user and uobj.is_admin != form.is_admin.data:
            flash("I can't let you change is_admin, {}".format(current_user.username))
        else:
            uobj.is_admin = form.is_admin.data
        uobj.save()
        flash('Updated user: ({}) {}'.format(uobj.id, uobj.username))
        current_app.logger.info('{} updated user ({}) {}'.format(current_user.username, uobj.id, uobj.username))
        return redirect(url_for('user.userdet'))
    return render_template('eduser.html', title='Update User: {}'.format(uid), form=form)

@user_bp.route('/userdet', methods=['GET'])
@login_required
@pw_check
@admin_only
def userdet():
    ulst = User.query.all()
    return render_template('udet.html', ulst=ulst, title='User Detail')

@user_bp.route('/images', methods=['GET'])
@login_required
@pw_check
@admin_only
def images():
    imgs = [(f,f[2:]) for f in listdir(STATIC) if f.startswith('T_')]
    return render_template('images.html', imgs=imgs, title='Images')

@user_bp.route('/nonimages', methods=['GET'])
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

@user_bp.route('/delimg/<fname>', methods=['GET'])
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
    return redirect(url_for('user.images'))

@user_bp.route('/delnonimg/<fname>', methods=['GET'])
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
    return redirect(url_for('user.nonimages'))

