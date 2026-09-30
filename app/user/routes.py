from . import db, user_bp
from .models import User
from .forms import RegistrationForm, LoginForm, ChPassForm, SettingsForm, clean_email
from flask import flash, render_template, redirect, url_for, request, current_app
from flask_login import current_user, login_user, login_required, logout_user
from flask_wtf import FlaskForm
from wtforms_sqlalchemy.orm import model_form
from functools import wraps
from secrets import token_urlsafe
from app.jsoncsrf import json_csrf_ok, form_csrf_ok, post_form_only

# Decorator to kick user back to mypage if already logged in
def logout_required(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if current_user.is_authenticated:
            flash('You are already logged in.')
            return redirect(url_for('user.mypage'))
        return func(*args, **kwargs)
    return inner

# Decorator to kick user back to mypage if not admin
def admin_only(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if not current_user.is_admin:
            flash('That page is for administrators only.', 'error')
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

# route to user homepage
@user_bp.route('/mypage')
@login_required
@pw_check
def mypage():
    from app.messages.routes import student_panel
    panel = student_panel(current_user) if not current_user.is_admin else None
    return render_template('mypage.html', current_user=current_user, panel=panel, title='My quizzes')

# route to user logout action
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

# route to user login action
@user_bp.route('/', methods=['POST','GET'])
@user_bp.route('/login', methods=['POST','GET'])
@logout_required
def login():
    from app.api.models import LoginFailure
    form = LoginForm()
    if form.validate_on_submit():
        #the same guard as the API: slow down password guessing
        if LoginFailure.too_many(form.username.data):
            flash('Too many wrong passwords. Please wait 15 minutes and try again.', 'error')
            return redirect(url_for('user.login'))
        u = User.query.filter_by(username=form.username.data).first()
        if u is None or not u.check_password(form.password.data):
            LoginFailure.record(form.username.data)
            flash('That username and password don\'t match.', 'error')
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

# route to user registration action
@user_bp.route('/register', methods=['POST','GET'])
@logout_required
def register():
    from app.qgen.models import Setting
    if not Setting.get('class_code'):
        return render_template('register_closed.html', title='Sign-up')
    form = RegistrationForm()
    if form.validate_on_submit():
        u = User(username=form.username.data, email=clean_email(form.email.data))
        u.set_password(form.password.data)
        u.save()
        current_app.logger.info('User {} has been created'.format(u.username))
        flash('Account {} registered'.format(form.username.data))
        return redirect(url_for('user.login'))
    else:
        return render_template('register.html', title='Register Now!', form=form)

# route to user password-change action
@user_bp.route('/chpass', methods=['POST','GET'])
@login_required
def chpass():
    form = ChPassForm()
    user = current_user
    if form.validate_on_submit():
        if not user.check_password(form.old_password.data):
            flash('Your current password was not right.', 'error')
            return redirect(url_for('user.chpass'))
        user.set_password(form.password.data)
        user.pw_man_reset = False
        user.save()
        flash('Password changed.', 'success')
        return redirect(url_for('user.mypage'))
    return render_template('chpass.html', title='Changing Password for {}'.format(user.username), form=form)

# route to admin-initiated user password-reset action
@user_bp.route('/resetpass/<uid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def resetpass(uid):
    usrquery = User.query.filter_by(id=uid)
    usr = usrquery.first_or_404('No user with id {}'.format(uid))
    #random one-time password, shown once to the admin and never logged
    pword = token_urlsafe(9)
    usr.set_password(pword)
    usr.pw_man_reset = True
    usr.save()
    flash('Password reset for {}. Temporary password: {} (they must change it at next login)'.format(usr.username, pword))
    current_app.logger.info('{} issued a manual PW reset for {}'.format(current_user.username, usr.username))
    return redirect(url_for('user.userdet'))

# route to admin-initiated user deletion action
@user_bp.route('/deluser/<uid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def deluser(uid):
    usrquery = User.query.filter_by(id=uid)
    usr = usrquery.first_or_404('No user with id {}'.format(uid))
    usrname = usr.username
    if current_user == usr:
        flash("I can't let you do that, {}".format(current_user.username))
        return redirect(url_for('user.userdet'))
    from . import avatars
    avatars.remove(usr, commit=False)
    usrquery.delete()
    db.session.commit()
    flash('User {} has been deleted'.format(usrname))
    current_app.logger.info('{} deleted user: {}'.format(current_user.username, usrname))
    return redirect(url_for('user.userdet'))

# route to admin-initiated user editing action
@user_bp.route('/edituser/<uid>', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def eduser(uid):
    uform = model_form(User, base_class=FlaskForm, db_session=db)
    uobj = User.query.filter_by(id=uid).first_or_404('No user with id {}'.format(uid))
    form = uform(obj=uobj)
    if request.method == 'POST':
        email = clean_email(form.email.data)
        taken = email and User.query.filter(User.email == email, User.id != uobj.id).first()
        if taken:
            flash('{} already uses that email address.'.format(taken.username), 'error')
            return render_template('eduser.html', title='Update User: {}'.format(uid), form=form)
        uobj.username = form.username.data
        uobj.email = email
        if uobj == current_user and uobj.is_admin != form.is_admin.data:
            flash("I can't let you change is_admin, {}".format(current_user.username))
        else:
            uobj.is_admin = form.is_admin.data
        uobj.save()
        flash('Updated user: ({}) {}'.format(uobj.id, uobj.username))
        current_app.logger.info('{} updated user ({}) {}'.format(current_user.username, uobj.id, uobj.username))
        return redirect(url_for('user.userdet'))
    return render_template('eduser.html', title='Update User: {}'.format(uid), form=form)

# route to admin-initiated user detail listing
@user_bp.route('/userdet', methods=['GET'])
@login_required
@pw_check
@admin_only
def userdet():
    ulst = User.query.order_by(User.username).all()
    return render_template('udet.html', ulst=ulst, title='Users')

# route to site-wide settings: name, logo, and the class code students need to sign up
@user_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@pw_check
@admin_only
def settings():
    from app.qgen.models import Setting
    form = SettingsForm()
    if request.method == 'GET':
        form.site_name.data = Setting.get('site_name', 'Quizzes')
        form.logo.data = Setting.get('logo', '')
        form.code.data = Setting.get('class_code', '')
    elif form.validate_on_submit():
        code = (form.code.data or '').strip()
        Setting.put('site_name', form.site_name.data.strip())
        Setting.put('logo', (form.logo.data or '').strip() or None)
        Setting.put('class_code', code or None)
        flash('Settings saved. ' + ('Students can sign up with the class code "{}".'.format(code) if code
              else 'Sign-up is off until you set a class code.'), 'success')
        current_app.logger.info('{} changed the site settings'.format(current_user.username))
        return redirect(url_for('user.settings'))
    return render_template('settings.html', form=form, title='Settings')


# ---------------------------------------------------------------- profile

# route to a user's own profile: picture and app tokens
@user_bp.route('/profile', methods=['GET'])
@login_required
@pw_check
def profile():
    from app.api.models import ApiToken
    tokens = ApiToken.query.filter_by(user_id=current_user.id).order_by(ApiToken.created.desc()).all()
    return render_template('profile.html', tokens=tokens, title='My profile')

# route to upload one's own picture (drag and drop on the profile page)
@user_bp.route('/profile/avatar', methods=['POST'])
@login_required
@pw_check
def upload_avatar():
    from flask import jsonify
    from . import avatars
    if not json_csrf_ok():
        return jsonify(ok=False, error='Your session expired. Please reload the page.'), 400
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify(ok=False, error='No picture received.'), 400
    try:
        name = avatars.save(current_user, f.stream)
    except avatars.AvatarError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    current_app.logger.info('{} changed their picture'.format(current_user.username))
    return jsonify(ok=True, name=name, url=url_for('static', filename=name))

# route to remove a picture: your own, or (teachers) anyone's
@user_bp.route('/avatar/remove/<int:uid>', methods=['POST'])
@login_required
@pw_check
def remove_avatar(uid):
    from . import avatars
    if not form_csrf_ok():
        flash('Your session expired. Please try again.', 'error')
        return redirect(request.referrer or url_for('user.mypage'))
    if uid != current_user.id and not current_user.is_admin:
        flash('You can only remove your own picture.', 'error')
        return redirect(url_for('user.mypage'))
    usr = User.query.filter_by(id=uid).first_or_404()
    avatars.remove(usr)
    flash('Picture removed{}.'.format('' if usr == current_user else ' for {}'.format(usr.username)), 'success')
    current_app.logger.info('{} removed the picture of {}'.format(current_user.username, usr.username))
    return redirect(request.referrer or url_for('user.profile'))

# route to create an app token from the profile page (shown once)
@user_bp.route('/profile/tokens', methods=['POST'])
@login_required
@pw_check
def create_token():
    from app.api.models import ApiToken
    if not form_csrf_ok():
        flash('Your session expired. Please try again.', 'error')
        return redirect(url_for('user.profile'))
    name = (request.form.get('name') or '').strip() or 'App'
    row, token = ApiToken.issue(current_user, name)
    current_app.logger.info('{} created API token {} ({})'.format(current_user.username, row.prefix, name))
    tokens = ApiToken.query.filter_by(user_id=current_user.id).order_by(ApiToken.created.desc()).all()
    #the token is only ever shown on this one page
    return render_template('profile.html', tokens=tokens, new_token=token, title='My profile')

# route to revoke one of your app tokens
@user_bp.route('/profile/tokens/<int:token_id>/revoke', methods=['POST'])
@login_required
@pw_check
def revoke_token(token_id):
    from app.api.models import ApiToken
    if not form_csrf_ok():
        flash('Your session expired. Please try again.', 'error')
        return redirect(url_for('user.profile'))
    row = db.session.get(ApiToken, token_id)
    if not row or row.user_id != current_user.id:
        flash('That token isn\'t yours.', 'error')
    else:
        row.revoked = True
        db.session.commit()
        flash('Token "{}" revoked: apps using it are signed out.'.format(row.name), 'success')
    return redirect(url_for('user.profile'))
