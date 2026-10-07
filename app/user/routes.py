from . import db, user_bp
from .models import User
from .forms import RegistrationForm, LoginForm, ChPassForm, SettingsForm, clean_email
from flask import flash, render_template, redirect, url_for, request, current_app, session, abort
from app.nav import back_to, safe_next, next_arg
from flask_login import current_user, login_user, login_required, logout_user
from flask_wtf import FlaskForm
from markupsafe import Markup
from wtforms_sqlalchemy.orm import model_form
from functools import wraps
from secrets import token_urlsafe
from app.jsoncsrf import json_csrf_ok, form_csrf_ok, post_form_only
from app.home import home_url

# Decorator to kick user back to mypage if already logged in
def logout_required(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if current_user.is_authenticated:
            flash('You are already logged in.')
            return redirect(home_url())
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
    #messages and notices are in the side panels every page has (see base.html)
    from app.qgen.models import mark_quizzes_seen, attempts_by_quiz, RETAKE_RULES_FOR_STUDENT
    from app.qgen import folders
    mark_quizzes_seen(current_user.id)
    groups = attempts_by_quiz(current_user.cquizzes)
    root, all_folders = folders.tree(current_user, groups)
    nodes, home = folders.index(root)
    #which part the side list has chosen: the quizzes in no folder (a quiz is in one place
    #only), 'all' (every quiz, each saying its folder), or a folder's id; a folder that's
    #gone (or isn't theirs) shows the quizzes in no folder
    from app import folder_tree
    #from Home's counters (?show=todo, started or soon): only those quizzes, from every folder
    showing = request.args.get('show') if request.args.get('show') in SHOW_ONLY else None
    if showing:
        view, node = folder_tree.view_of('all', nodes, remember=False)
    else:
        view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='main', extra=('new',))
    #the automatic "New" folder: quizzes given to them and not started yet (each also stays in its own folder)
    fresh = [g for g in groups if any(a.status == 'new' for a in g['attempts'])]
    shown = node['groups'] if node else groups if view == 'all' else fresh if view == 'new' else root['groups']
    if showing:
        from app import tuning
        from app.qgen.models import waiting_quizzes
        from datetime import datetime
        now = datetime.now()
        waiting = waiting_quizzes(current_user, now)
        wanted = {cq.id for cq in waiting if
                  (showing == 'todo' and cq.status == 'new') or (showing == 'started' and cq.status == 'started')
                  or (showing == 'soon' and cq.closes_at and now <= cq.closes_at <= now + tuning.due_soon())}
        shown = [g for g in groups if any(a.id in wanted for a in g['attempts'])]
        days = tuning.get('due_soon_days')
        within = '{} day{}'.format(days, '' if days == 1 else 's')
        heading, nothing = {
            'todo': ('📝 To do: quizzes you haven’t started', 'You have no quizzes waiting to be started. 🎉'),
            'started': ('✏️ Started: quizzes you haven’t handed in', 'You have no quizzes started and not handed in. 🎉'),
            'soon': ('⏰ Due within {}'.format(within), 'Nothing is due within {}. 🎉'.format(within)),
        }[showing]
    elif view == 'new':
        heading, nothing = '🆕 New: quizzes you haven’t started', 'No new quizzes right now. 🎉'
    else:
        heading = nothing = None
    fk = folder_tree.kit(
        view, node, root, all_folders, nodes,
        page=lambda v: url_for('user.mypage', folder=v),
        create_url=url_for('user.create_folder'), move_url=url_for('user.move_to_folder'),
        rename_url=lambda fid: url_for('user.rename_folder', folder_id=fid),
        delete_url=lambda fid: url_for('user.delete_folder', folder_id=fid),
        unit='quiz', units='quizzes', all_label='All quizzes', all_count=len(groups), main_count=len(root['groups']),
        name=lambda f: f.name, add_words='Move to…', drag_what='a quiz',
        hint='Your own folders: nobody else sees them. A quiz is in one place at a time.',
        fold_key='qgen-folded-folders', open_key='qgen-open-subfolders', title=heading,
        new_view={'label': 'New', 'count': len(fresh)},
        purge_url=lambda fid: url_for('user.purge_folder', folder_id=fid),
        purge_blocked=lambda n: folders.not_handed_in_note(folders.not_handed_in(current_user, n['folder'].id)),
        purge_question=lambda n: 'Delete the folder “{}”{} and the {} quiz{} in it? {} go{} to your teacher, who can '
                                 'give {} back. Your answers and scores go with {}.'.format(
            n['folder'].name, ' and the folders inside it' if n['folders'] else '', n['count'], '' if n['count'] == 1 else 'zes',
            'It' if n['count'] == 1 else 'They', 'es' if n['count'] == 1 else '', 'it' if n['count'] == 1 else 'them',
            'it' if n['count'] == 1 else 'them') if n['count'] else
            'Delete the folder “{}”{}? It’s empty.'.format(n['folder'].name, ' and the folders inside it' if n['folders'] else ''))
    #the last few handed in (any folder, any time), newest first, above the folders
    finished = sorted((cq for cq in current_user.cquizzes if cq.status in ('completed', 'review') and cq.compdate),
                      key=lambda cq: cq.compdate, reverse=True)[:LATEST_FINISHED]
    return render_template('mypage.html', current_user=current_user, student_rules=RETAKE_RULES_FOR_STUDENT, title='My quizzes',
                           groups=groups, fk=fk, shown=shown, home=home, finished=finished,
                           showing=showing, nothing=nothing)


def _folder_done(message, error=False, show=None, moved=None):
    """After a folder change: JSON for the page's script (drag and drop), else back to My quizzes
    showing the same folder (or `show`: a folder's id, or 'main')."""
    if request.headers.get('X-Requested-With') == 'fetch':
        from flask import jsonify
        return (jsonify(ok=False, error=message), 400) if error else jsonify(ok=True, message=message)
    flash(message, 'error' if error else 'success')
    if show is None:
        show = request.form.get('view') or 'main'
    values = {'folder': show}
    if moved and not error:
        values['moved'] = moved  # lit up on the page, like after a drag
    return redirect(url_for('user.mypage', **values))


#routes for one's own folders on My quizzes (students and teachers alike)
@user_bp.route('/mypage/folders', methods=['POST'])
@login_required
@pw_check
@post_form_only
def create_folder():
    from app.qgen import folders
    try:
        f = folders.create_folder(current_user, request.form.get('name'), request.form.get('parent'))
    except folders.FolderError as exc:
        return _folder_done(str(exc), error=True)
    return _folder_done('Folder "{}" made.'.format(f.name))  # stay where you were


@user_bp.route('/mypage/folders/<int:folder_id>/rename', methods=['POST'])
@login_required
@pw_check
@post_form_only
def rename_folder(folder_id):
    from app.qgen import folders
    try:
        f = folders.rename_folder(current_user, folder_id, request.form.get('name'))
    except folders.FolderError as exc:
        return _folder_done(str(exc), error=True)
    return _folder_done('Folder renamed to "{}".'.format(f.name))


@user_bp.route('/mypage/folders/<int:folder_id>/delete', methods=['POST'])
@login_required
@pw_check
@post_form_only
def delete_folder(folder_id):
    from app.qgen import folders
    from app.qgen.models import QuizFolder
    f = db.session.get(QuizFolder, folder_id)
    parent = f.parent_id if f is not None and f.owner_id == current_user.id else None
    try:
        name = folders.delete_folder(current_user, folder_id)
    except folders.FolderError as exc:
        return _folder_done(str(exc), error=True)
    return _folder_done('Folder "{}" removed; what was in it moved up a level.'.format(name),
                        show=(parent or 'main') if request.form.get('view') == str(folder_id) else None)


#delete a folder with the folders and quizzes in it (the quizzes go to the Archive)
@user_bp.route('/mypage/folders/<int:folder_id>/purge', methods=['POST'])
@login_required
@pw_check
@post_form_only
def purge_folder(folder_id):
    from app.qgen import folders
    from app.qgen.models import QuizFolder
    f = db.session.get(QuizFolder, folder_id)
    parent = f.parent_id if f is not None and f.owner_id == current_user.id else None
    try:
        name, count = folders.delete_folder_and_quizzes(current_user, folder_id)
    except folders.FolderError as exc:
        return _folder_done(str(exc), error=True)
    return _folder_done('Deleted the folder "{}"{}.'.format(
        name, ' and its {} quiz{} (your teacher can give {} back)'.format(count, '' if count == 1 else 'zes', 'it' if count == 1 else 'them') if count else ''),
        show=(parent or 'main') if request.form.get('view') == str(folder_id) else None)


#move a quiz (quiz=<quiz id>) or a folder (folder=<id>) into a folder (to=<id>, or "top": the main list)
@user_bp.route('/mypage/move', methods=['POST'])
@login_required
@pw_check
@post_form_only
def move_to_folder():
    from app.qgen import folders
    from app.qgen.models import QuizFolder, VQuiz
    to = request.form.get('to')
    try:
        if request.form.get('folder'):
            target = folders.move_folder(current_user, request.form.get('folder'), to)
            what = db.session.get(QuizFolder, int(request.form.get('folder'))).name
            where = '"{}"'.format(target.name) if target else 'the top'
            moved = 'folder:{}'.format(request.form.get('folder'))
        else:
            target = folders.move_quiz(current_user, request.form.get('quiz'), to)
            what = db.session.get(VQuiz, int(request.form.get('quiz'))).title
            where = '"{}"'.format(target.name) if target else 'Not in a folder'
            moved = 'quiz:{}'.format(request.form.get('quiz'))
    except folders.FolderError as exc:
        return _folder_done(str(exc), error=True)
    return _folder_done('Moved "{}" to {}.'.format(what, where), moved=moved)

#Home's "Recently completed": how far back, and how many at most
RECENT_DAYS, RECENT_MAX = 14, 10
#how many of the latest handed-in quizzes My quizzes lists at the top
LATEST_FINISHED = 3
#My quizzes ?show=: Home's counters open it showing only these (the page otherwise looks as usual)
SHOW_ONLY = ('todo', 'started', 'soon')

# route to a student's Home: what's waiting for them, and the awards they've earned
@user_bp.route('/home')
@login_required
@pw_check
def home():
    from datetime import datetime, timedelta
    from app import tuning
    from app.qgen import awards
    now = datetime.now()
    from app.qgen.models import waiting_quizzes
    #what to do next: the ones closing soonest first, then the rest, oldest first
    waiting = waiting_quizzes(current_user, now)
    soon = [cq for cq in waiting if cq.closes_at and now <= cq.closes_at <= now + tuning.due_soon()]
    have = awards.earned(current_user)
    #handed in during the last two weeks, newest first (at most 10); being graded included
    since = now - timedelta(days=RECENT_DAYS)
    recent = sorted((cq for cq in current_user.cquizzes if cq.status in ('completed', 'review') and cq.compdate and cq.compdate >= since),
                    key=lambda cq: cq.compdate, reverse=True)[:RECENT_MAX]
    return render_template('home.html', title='Home', now=now, waiting=waiting, soon=soon, recent=recent, recent_days=RECENT_DAYS,
                           todo=sum(1 for cq in waiting if cq.status == 'new'),
                           started=sum(1 for cq in waiting if cq.status == 'started'),
                           awards=have, to_earn=awards.still_to_earn(current_user, have))

# route to user logout action
@user_bp.route('/logout')
@login_required
@pw_check
def logout():
    flash('{} has been logged out'.format(current_user.shown_name))
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
            from app import tuning
            flash('Too many wrong passwords. Please wait {} minutes and try again.'.format(tuning.get('lockout_minutes')), 'error')
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
        #the first page after signing in says what's waiting (messages.js)
        session['qgen_welcome'] = True
        #only a page on this site (a link could otherwise send them elsewhere after signing in)
        return redirect(safe_next(request.args.get('next'), home_url()))
    return render_template('login.html', title='Log in', form=form)

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
        from app.messages.models import notify_teachers
        notify_teachers(u.id, 'New student signed up: {}.'.format(u.shown_name), url_for('qgen.list_user', uid=u.id))
        db.session.commit()
        current_app.logger.info('User {} has been created'.format(u.username))
        flash('Account {} registered'.format(form.username.data))
        return redirect(url_for('user.login'))
    else:
        return render_template('register.html', title='Create an account', form=form)

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
        return redirect(home_url())
    return render_template('chpass.html', title='Change password', form=form)

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
    flash('Password reset for {}. Temporary password: {} (it must be changed at the next login)'.format(usr.shown_name, pword))
    current_app.logger.info('{} issued a manual PW reset for {}'.format(current_user.username, usr.username))
    return redirect(back_to(url_for('user.userdet')))

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
        flash("I can't let you do that, {}".format(current_user.shown_name))
        return redirect(url_for('user.userdet'))
    from . import avatars
    from app.qgen import services as S
    #their quiz attempts are kept in the archive
    S.archive_student(usr, by=current_user)
    avatars.remove(usr, commit=False)
    usrquery.delete()
    db.session.commit()
    flash('User {} has been deleted'.format(usrname))
    current_app.logger.info('{} deleted user: {}'.format(current_user.username, usrname))
    #back to the Users page they were on (its folder), not to the deleted person's pages
    users = url_for('user.userdet')
    back = back_to(users)
    return redirect(back if back.split('?')[0] == users else users)

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
            flash('{} already uses that email address.'.format(taken.shown_name), 'error')
            return render_template('eduser.html', title='Edit user: {}'.format(uobj.shown_name), form=form)
        uobj.username = form.username.data
        uobj.email = email
        if uobj == current_user and uobj.is_admin != form.is_admin.data:
            flash("I can't let you change is_admin, {}".format(current_user.shown_name))
        else:
            uobj.is_admin = form.is_admin.data
        uobj.save()
        flash('Updated user: ({}) {}'.format(uobj.id, uobj.shown_name))
        current_app.logger.info('{} updated user ({}) {}'.format(current_user.username, uobj.id, uobj.username))
        return redirect(next_arg(url_for('user.userdet')))
    return render_template('eduser.html', title='Edit user: {}'.format(uobj.shown_name), form=form)

# route to admin-initiated user detail listing
@user_bp.route('/userdet', methods=['GET'])
@login_required
@pw_check
@admin_only
def userdet():
    from . import groups
    from app import folder_tree
    ulst = User.query.order_by(User.username).all()
    root, flat, nodes, folders_of = groups.tree(ulst)
    #the people in no folder (the default), 'all', or a folder's id (a gone folder: in no folder)
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='main')
    shown = node['people'] if node else ulst if view == 'all' else root['people']
    fk = folder_tree.kit(
        view, node, root, flat, nodes,
        page=lambda v: url_for('user.userdet', folder=v),
        create_url=url_for('user.create_user_folder'), move_url=url_for('user.move_user_or_folder'),
        rename_url=lambda fid: url_for('user.rename_user_folder', folder_id=fid),
        delete_url=lambda fid: url_for('user.delete_user_folder', folder_id=fid),
        add_url=url_for('user.add_to_user_folder'), remove_url=url_for('user.remove_from_user_folder'),
        unit='person', units='people', all_label='All users', all_count=len(ulst), name=lambda f: f.name,
        placeholder='e.g. 7th grade', add_words='+ Add…', drag_what='a person',
        hint='Folders are shared by all teachers; students never see them. Someone can be in several folders.',
        box_tools=lambda n: Markup('<a href="{}">Assign a quiz to this folder</a> · ').format(url_for('qgen.assign', folder=n['folder'].id))
        if n['count'] else '',
        fold_key='qgen-folded-user-folders', open_key='qgen-open-user-subfolders')
    return render_template('udet.html', ulst=ulst, title='Users', fk=fk, shown=shown, folders_of=folders_of)


def _group_done(message, error=False, show=None, moved=None):
    """After a change to the Users page's folders: JSON for the page's script, else back to
    the Users page showing the same folder (or `show`)."""
    if request.headers.get('X-Requested-With') == 'fetch':
        from flask import jsonify
        return (jsonify(ok=False, error=message), 400) if error else jsonify(ok=True, message=message)
    flash(message, 'error' if error else 'success')
    if show is None:
        show = request.form.get('view') or 'main'
    show = str(show)
    values = {'folder': show} if show.isdigit() or show == 'all' else {}
    if moved and not error:
        values['moved'] = moved  # lit up on the page, like after a drag
    return redirect(url_for('user.userdet', **values))


#routes for the Users page's folders (shared by the teachers)
@user_bp.route('/users/folders', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def create_user_folder():
    from . import groups
    try:
        f = groups.create(request.form.get('name'), request.form.get('parent'))
    except groups.GroupError as exc:
        return _group_done(str(exc), error=True)
    return _group_done('Folder "{}" made.'.format(f.name))  # stay where you were


@user_bp.route('/users/folders/<int:folder_id>/rename', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def rename_user_folder(folder_id):
    from . import groups
    try:
        f = groups.rename(folder_id, request.form.get('name'))
    except groups.GroupError as exc:
        return _group_done(str(exc), error=True)
    return _group_done('Folder renamed to "{}".'.format(f.name))


@user_bp.route('/users/folders/<int:folder_id>/delete', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delete_user_folder(folder_id):
    from . import groups
    from .models import UserFolder
    f = db.session.get(UserFolder, folder_id)
    parent = f.parent_id if f is not None else None
    try:
        name = groups.remove(folder_id)
    except groups.GroupError as exc:
        return _group_done(str(exc), error=True)
    return _group_done('Folder "{}" removed; everyone in it moved up a level.'.format(name),
                       show=(parent or 'main') if request.form.get('view') == str(folder_id) else None)


#dragging: a person onto a folder (from a folder: moved out of that one; from the main list
#or All users: put in it), onto the main list (out of the folder shown, or out of every
#folder); or a folder onto a folder ("top": the top level). Also the folder's "Move to" list.
@user_bp.route('/users/folders/move', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def move_user_or_folder():
    from . import groups
    from .models import UserFolder
    to, came_from = request.form.get('to'), request.form.get('from') or ''
    here = came_from if came_from.isdigit() else None  # the folder it was dragged out of
    try:
        if request.form.get('folder'):
            target = groups.move_folder(request.form.get('folder'), to)
            name = db.session.get(UserFolder, int(request.form.get('folder'))).name
            message = 'Moved "{}" to {}.'.format(name, '"{}"'.format(target.name) if target else 'the top level')
        elif to in (None, '', 'top', 'main'):
            person, f = groups.take_out(request.form.get('user'), here)
            message = ('Took {} out of "{}".'.format(person.shown_name, f.name) if f
                       else 'Took {} out of every folder.'.format(person.shown_name))
        else:
            person, f = groups.add(request.form.get('user'), to, moving_from=here)
            message = 'Moved {} to "{}".'.format(person.shown_name, f.name) if here else \
                'Put {} in "{}".'.format(person.shown_name, f.name)
    except groups.GroupError as exc:
        return _group_done(str(exc), error=True)
    return _group_done(message, moved='folder:{}'.format(request.form.get('folder')) if request.form.get('folder')
                       else 'user:{}'.format(request.form.get('user')))


#a person's "Add to folder" list (they stay in their other folders) and a folder's ✕
@user_bp.route('/users/folders/add', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def add_to_user_folder():
    from . import groups
    try:
        person, f = groups.add(request.form.get('user'), request.form.get('to'))
    except groups.GroupError as exc:
        return _group_done(str(exc), error=True)
    return _group_done('Put {} in "{}".'.format(person.shown_name, f.name), moved='user:{}'.format(person.id))


@user_bp.route('/users/folders/remove', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def remove_from_user_folder():
    from . import groups
    try:
        person, f = groups.take_out(request.form.get('user'), request.form.get('folder'))
    except groups.GroupError as exc:
        return _group_done(str(exc), error=True)
    return _group_done('Took {} out of "{}".'.format(person.shown_name, f.name) if f else
                       'Took {} out of every folder.'.format(person.shown_name))

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
        form.favicon.data = Setting.get('favicon', '')
        form.code.data = Setting.get('class_code', '')
    elif form.validate_on_submit():
        code = (form.code.data or '').strip()
        Setting.put('site_name', form.site_name.data.strip())
        Setting.put('logo', (form.logo.data or '').strip() or None)
        Setting.put('favicon', (form.favicon.data or '').strip() or None)
        Setting.put('class_code', code or None)
        flash('Settings saved. ' + ('Students can sign up with the class code "{}".'.format(code) if code
              else 'Sign-up is off until you set a class code.'), 'success')
        current_app.logger.info('{} changed the site settings'.format(current_user.username))
        return redirect(url_for('user.settings'))
    return render_template('settings.html', form=form, title='Settings')


# the picture in the browser tab: /favicon.ico for browsers that ask for it by that name,
# and sized copies the pages link to (their address changes when the picture does)
@user_bp.route('/favicon.ico')
def favicon():
    return site_icon_png(32, cache=24 * 3600)

@user_bp.route('/site-icon/<int:size>.png')
def site_icon(size):
    from app import site_icon as icon
    if size not in icon.SIZES:
        abort(404)
    return site_icon_png(size, cache=365 * 24 * 3600 if request.args.get('v') else 3600)

def site_icon_png(size, cache):
    from app import site_icon as icon
    name = icon.chosen()
    if name and icon.is_svg(name) and size == 32:
        resp = current_app.send_static_file(name)
    else:
        data = icon.png(name, size)
        if data is None:
            abort(404)
        resp = current_app.response_class(data, mimetype='image/png')
    resp.cache_control.public = True
    resp.cache_control.max_age = cache
    return resp


# route to the technical settings: time spans, limits and the AI model (app/tuning.py)
@user_bp.route('/settings/technical', methods=['GET'])
@login_required
@pw_check
@admin_only
def technical_settings():
    from app import tuning
    return render_technical(tuning.values(), {})

def render_technical(shown, errors):
    from app import tuning
    groups = [(key, label, [t for t in tuning.TUNABLES if t['group'] == key]) for key, label in tuning.GROUPS]
    return render_template('settings_technical.html', title='Technical settings', groups=groups, shown=shown,
                           errors=errors, current=tuning.values(),
                           current_changed=[k for k, v in tuning.values().items() if v != tuning.BY_KEY[k]['default']])

# route to save the technical settings (all or nothing)
@user_bp.route('/settings/technical', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def save_technical_settings():
    from app import tuning
    if request.form.get('reset'):
        key = request.form['reset']
        if key == 'all':
            tuning.reset(current_user)
            flash('All technical settings are back to their defaults.', 'success')
        elif key in tuning.BY_KEY:
            tuning.reset(current_user, key)
            flash('"{}" is back to its default.'.format(tuning.BY_KEY[key]['label']), 'success')
        return redirect(url_for('user.technical_settings'))
    chosen, errors = tuning.validate(request.form)
    if errors:
        flash('Nothing was saved: please fix the {} marked below.'.format('one' if len(errors) == 1 else 'ones'), 'error')
        return render_technical({t['key']: request.form.get(t['key'], '') for t in tuning.TUNABLES}, errors), 400
    changed = tuning.save(chosen, current_user)
    flash('Saved {} change{}.'.format(len(changed), '' if len(changed) == 1 else 's') if changed else 'Nothing changed.', 'success')
    return redirect(url_for('user.technical_settings'))

# ---------------------------------------------------------------- profile

# route to a user's own profile: picture and app tokens
@user_bp.route('/profile', methods=['GET'])
@login_required
@pw_check
def profile():
    from app.api.models import ApiToken
    tokens = ApiToken.query.filter_by(user_id=current_user.id).order_by(ApiToken.created.desc()).all() if current_user.is_admin else []
    return render_template('profile.html', tokens=tokens, title='My profile')

def clean_nickname(text):
    """A nickname as it's kept: spaces tidied, None for none. Raises ValueError (the reason,
    to show) if it's too long, or is someone else's username (it could pass for them)."""
    nick = ' '.join(str(text or '').split())
    if not nick:
        return None
    if len(nick) > User.NICKNAME_MAX:
        raise ValueError('A nickname can be at most {} characters.'.format(User.NICKNAME_MAX))
    if any(ord(c) < 32 for c in nick):
        raise ValueError('Please use ordinary letters, numbers and spaces.')
    taken = User.query.filter(db.func.lower(User.username) == nick.lower(), User.id != current_user.id).first()
    if taken:
        raise ValueError('That is someone else\'s name here. Please choose another nickname.')
    return nick

# route to set (or clear) one's own nickname; nobody else can set it
@user_bp.route('/profile/nickname', methods=['POST'])
@login_required
@pw_check
@post_form_only
def set_nickname():
    try:
        nick = None if request.form.get('clear') else clean_nickname(request.form.get('nickname'))
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('user.profile'))
    if nick == current_user.nickname:
        return redirect(url_for('user.profile'))
    current_user.nickname = nick
    db.session.commit()
    flash('Your nickname is now "{}".'.format(nick) if nick else 'Your nickname is gone; your name shows on its own.', 'success')
    current_app.logger.info('{} {} their nickname'.format(current_user.username, 'set' if nick else 'cleared'))
    return redirect(url_for('user.profile'))

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
    current_app.logger.info('{} uploaded a new profile picture'.format(current_user.username))
    return jsonify(ok=True, name=name, url=url_for('static', filename=name))

# route to remove a picture: your own, or (teachers) anyone's
@user_bp.route('/avatar/remove/<int:uid>', methods=['POST'])
@login_required
@pw_check
def remove_avatar(uid):
    from . import avatars
    if not form_csrf_ok():
        flash('Your session expired. Please try again.', 'error')
        return redirect(back_to(home_url()))
    if uid != current_user.id and not current_user.is_admin:
        flash('You can only remove your own picture.', 'error')
        return redirect(url_for('user.mypage'))
    usr = User.query.filter_by(id=uid).first_or_404()
    avatars.remove(usr)
    flash('Picture removed{}.'.format('' if usr == current_user else ' for {}'.format(usr.username)), 'success')
    current_app.logger.info('{} removed the picture of {}'.format(current_user.username, usr.username))
    return redirect(back_to(url_for('user.profile')))

# route to create an app token from the profile page (shown once); teachers only
@user_bp.route('/profile/tokens', methods=['POST'])
@login_required
@pw_check
@admin_only
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

# route to revoke one of your app tokens; teachers only
@user_bp.route('/profile/tokens/<int:token_id>/revoke', methods=['POST'])
@login_required
@pw_check
@admin_only
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
