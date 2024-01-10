from app import app
from app.models import User
from app.forms import RegistrationForm, LoginForm, UploadForm
from flask import flash, render_template, redirect, url_for, request
from flask_login import current_user, login_user, login_required, logout_user
from werkzeug.utils import secure_filename
from functools import wraps

# Decorator to kick user back to mypage if already logged in
def logout_required(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if current_user.is_authenticated:
            flash('{} unavailable while logged in'.format(url_for(func.__name__)))
            return redirect(url_for('mypage'))
        return func(*args, **kwargs)
    return inner


@app.route('/mypage')
@login_required
def mypage():
    return render_template('mypage.html', title='{}\'s Page'.format(current_user.username))


@app.route('/logout')
@login_required
def logout():
    flash('{} has been logged out'.format(current_user.username))
    logout_user()
    return redirect(url_for('login'))


@app.route('/upload', methods=['POST','GET'])
@login_required
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
        flash('Account {} registered'.format(form.username.data))
        return redirect(url_for('login'))
    else:
        return render_template('register.html', title='Register Now!', form=form)

