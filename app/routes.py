from app import app, db
from app.models import User
from app.forms import RegistrationForm, LoginForm, UploadForm, ChPassForm
from flask import flash, render_template, redirect, url_for, request
from flask_login import current_user, login_user, login_required, logout_user
from flask_wtf import FlaskForm
from wtforms_sqlalchemy.orm import model_form
from werkzeug.utils import secure_filename
from functools import wraps

# Decorator to kick user back to mypage if already logged in
def logout_required(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if current_user.is_authenticated:
            flash('{} is unavailable while logged in'.format(request.__dict__['environ']['RAW_URI']))
            return redirect(url_for('mypage'))
        return func(*args, **kwargs)
    return inner

# Decorator to kick user back to mypage if not admin
def admin_only(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if not current_user.is_admin:
            flash('{} is available to administrators only'.format(request.__dict__['environ']['RAW_URI']))
            return redirect(url_for('mypage'))
        return func(*args, **kwargs)
    return inner

# Decorator to kick user back to password change after manual reset
def pw_check(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if current_user.pw_man_reset:
            flash('Please change your password before continuing')
            return redirect(url_for('chpass'))
        else:
            return func(*args, **kwargs)
    return inner

@app.route('/mypage')
@login_required
@pw_check
def mypage():
    return render_template('mypage.html', current_user=current_user, title='{}\'s Page'.format(current_user.username))

@app.route('/logout')
@login_required
@pw_check
def logout():
    flash('{} has been logged out'.format(current_user.username))
    app.logger.info('{} has logged out'.format(current_user.username))
    logout_user()
    return redirect(url_for('login'))

@app.route('/upload', methods=['POST','GET'])
@login_required
@pw_check
@admin_only
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        ufile = request.files['thefile']
        #need to generalize this
        ufile.save('/home/dan/proj/quiz/app/static/{}'.format(secure_filename(ufile.filename)))
        flash('{} saved'.format(ufile.filename))
        return redirect(url_for('mypage'))
    return render_template('upload.html', title='Upload a File', form=form)

@app.route('/', methods=['POST','GET'])
@app.route('/login', methods=['POST','GET'])
@logout_required
def login():
    form = LoginForm()
    if form.validate_on_submit():
        u = User.query.filter_by(username=form.username.data).first()
        if u is None or not u.check_password(form.password.data):
            flash('Invalid Username/Password')
            return redirect(url_for('login')) 
        login_user(u, remember=True)
        app.logger.info('{} has logged in'.format(u.username))
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('mypage'))
    return render_template('login.html', title='Login Now!', form=form)

@app.route('/register', methods=['POST','GET'])
@logout_required
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        u = User(username=form.username.data, email=form.email.data)
        u.set_password(form.password.data)
        u.save()
        app.logger.info('User {} has been created'.format(u.username))
        flash('Account {} registered'.format(form.username.data))
        return redirect(url_for('login'))
    else:
        return render_template('register.html', title='Register Now!', form=form)

@app.route('/chpass', methods=['POST','GET'])
@login_required
def chpass():
    form = ChPassForm()
    user = current_user
    if form.validate_on_submit():
        if not user.check_password(form.old_password.data):
            flash('Old Password Error')
            return redirect(url_for('chpass'))
        user.set_password(form.password.data)
        user.pw_man_reset = False
        user.save()
        flash('Password changed')
        return redirect(url_for('mypage'))
    return render_template('chpass.html', title='Changing Password for {}'.format(user.username), form=form)

@app.route('/resetpass/<uid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def resetpass(uid):
    usrquery = User.query.filter_by(id=uid)
    usr = usrquery.first_or_404('No user with id {}'.format(uid))
    usr.set_password('PASSWORD')
    usr.pw_man_reset = True
    usr.save()
    flash('Password reset for {}'.format(usr.username))
    return redirect(url_for('userdet'))

@app.route('/deluser/<uid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def deluser(uid):
    usrquery = User.query.filter_by(id=uid)
    usr = usrquery.first_or_404('No user with id {}'.format(uid))
    usrname = usr.username
    if current_user == usr:
        flash("I can't let you do that, {}".format(current_user.username))
        return redirect(url_for('userdet'))
    usrquery.delete()
    db.session.commit()
    app.logger.info('User {} has been deleted'.format(usrname))
    flash('Deleted user: {}'.format(usrname))
    return redirect(url_for('userdet'))

@app.route('/edituser/<uid>', methods=['POST', 'GET'])
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
        msg = 'Updated user: ({}) {}'.format(uobj.id, uobj.username)
        flash(msg)
        app.logger.info(msg)
        return redirect(url_for('userdet'))
    return render_template('eduser.html', title='Update User: {}'.format(uid), form=form)

@app.route('/quiz/userdet', methods=['GET'])
@login_required
@pw_check
@admin_only
def userdet():
    ulst = User.query.all()
    return render_template('udet.html', ulst=ulst, title='User Detail')

