from . import db, user_bp
from .models import User
from .forms import RegistrationForm, LoginForm, ChPassForm, SettingsForm, clean_email
from flask import flash, render_template, redirect, url_for, request, current_app, session, abort
from app.nav import back_to, safe_next, next_arg, kept_tab
from flask_login import current_user, login_user, login_required, logout_user
from flask_wtf import FlaskForm
from markupsafe import Markup
from app.icons import icon_label
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
            #(the site's own address, "/", just goes home, with nothing said: the user critic, 2026-10-20)
            if request.path != '/':
                flash('You’re already logged in.', 'info')
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
            flash('Please change your password before going on.', 'warning')
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
    #"due": not handed in yet and closing within the due-soon time (as Home counts them)
    from app import tuning
    from app.qgen.models import waiting_quizzes
    from datetime import datetime
    now = datetime.now()
    waiting = waiting_quizzes(current_user, now)
    due_ids = {cq.id for cq in waiting if cq.closes_at and now <= cq.closes_at <= now + tuning.due_soon()}
    root, all_folders = folders.tree(current_user, groups, due_ids)
    nodes, home = folders.index(root)
    #which part the side list has chosen: 'all' (the default: every quiz, each saying its folder),
    #the quizzes in no folder (a quiz is in one place only), or a folder's id; a folder that's
    #gone (or isn't theirs) shows them all
    from app import folder_tree
    #from Home's counters (?show=todo, started or soon): only those quizzes, from every folder
    showing = request.args.get('show') if request.args.get('show') in SHOW_ONLY else None
    if showing:
        view, node = folder_tree.view_of('all', nodes, remember=False)
    else:
        view, node = folder_tree.view_of(folder_tree.choice_of(request.args), nodes, default='all', extra=('new', 'started'))
    #the automatic "New" folder: quizzes given to them and not started yet (each also stays in its own folder)
    fresh = [g for g in groups if any(a.status == 'new' for a in g['attempts'])]
    #and "In progress": started and not handed in yet, or handed in and waiting to be graded
    #(also each in its own folder)
    working = [g for g in groups if any(a.status in ('started', 'review') for a in g['attempts'])]
    days = tuning.get('due_soon_days')
    within = '{} day{}'.format(days, '' if days == 1 else 's')
    #their badges count tries (a quiz given twice and not started is 2 new)
    tries = {'new': sum(1 for g in groups for a in g['attempts'] if a.status == 'new'),
             'started': sum(1 for g in groups for a in g['attempts'] if a.status in ('started', 'review'))}
    def n_tries(n):
        return '{} {}'.format(n, 'attempt' if n == 1 else 'attempts')
    shown = (node['groups'] if node else groups if view == 'all' else fresh if view == 'new'
             else working if view == 'started' else root['groups'])
    if showing:
        wanted = {cq.id for cq in current_user.cquizzes if
                  (showing == 'todo' and cq.status == 'new') or (showing == 'started' and cq.status in ('started', 'review'))
                  or (showing == 'soon' and cq.status in ('new', 'started') and cq.closes_at and now <= cq.closes_at <= now + tuning.due_soon())}
        shown = [g for g in groups if any(a.id in wanted for a in g['attempts'])]
        heading, nothing = {
            'todo': ('To do: quizzes you haven’t started', 'You have no quizzes waiting to be started.'),
            'started': ('In progress: quizzes you’ve started, or handed in and not graded yet', 'Nothing in progress right now.'),
            'soon': ('Due within {}'.format(within), 'Nothing is due within {}.'.format(within)),
        }[showing]
    elif view == 'new':
        heading, nothing = 'New: quizzes you haven’t started', 'No new quizzes right now.'
    elif view == 'started':
        heading, nothing = 'In progress: quizzes you’ve started, or handed in and not graded yet', 'Nothing in progress right now.'
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
        fold_key='qgen-folded-folders', title=heading,
        #the automatic folders, always in this order (the teacher's view of a student too): New, In progress
        auto_views=[{'key': 'new', 'icon': 'sparkle', 'label': 'New', 'count': tries['new'], 'badge': '{} new'.format(tries['new']),
                     'badge_title': '{} not started yet'.format(n_tries(tries['new']))},
                    {'key': 'started', 'icon': 'pencil', 'label': 'In progress', 'count': tries['started'],
                     'badge': '{} in progress'.format(tries['started']), 'badge_class': 'badge-accent',
                     'badge_title': '{} started, or handed in and not graded yet'.format(n_tries(tries['started']))}],
        purge_url=lambda fid: url_for('user.purge_folder', folder_id=fid),
        purge_blocked=lambda n: folders.not_handed_in_note(folders.not_handed_in(current_user, n['folder'].id)),
        purge_question=lambda n: 'Delete the folder “{}”{} and the {} quiz{} in it? {} go{} to your teacher, who can '
                                 'give {} back. Your answers and scores go with {}.'.format(
            n['folder'].name, ' and the folders inside it' if n['folders'] else '', n['count'], '' if n['count'] == 1 else 'zes',
            'It' if n['count'] == 1 else 'They', 'es' if n['count'] == 1 else '', 'it' if n['count'] == 1 else 'them',
            'it' if n['count'] == 1 else 'them') if n['count'] else
            'Delete the folder “{}”{}? It’s empty.'.format(n['folder'].name, ' and the folders inside it' if n['folders'] else ''))
    #the folder tabs over their one list of quizzes (static/js/folderfilter.js), as on every
    #folder page: All quizzes, New, In progress, their folders, then Uncategorized
    def keys(gs):
        return sorted('quiz:{}'.format(g['vquiz'].id) for g in gs)
    def under(n):
        return n['groups'] + [g for c in n['folders'] for g in under(c)]
    def tab(n):
        return {'id': n['folder'].id, 'name': n['folder'].name, 'count': n['count'], 'url': url_for('user.mypage', folder=n['folder'].id),
                'keys': keys(under(n)), 'children': [tab(c) for c in n['folders']]}
    quiz_filter = ([{'id': 'new', 'name': 'New', 'icon': 'sparkle', 'count': len(fresh), 'keys': keys(fresh), 'children': [],
                     'url': url_for('user.mypage', folder='new'), 'empty': 'No new quizzes right now.'},
                    {'id': 'started', 'name': 'In progress', 'icon': 'pencil', 'count': len(working), 'keys': keys(working), 'children': [],
                     'url': url_for('user.mypage', folder='started'), 'empty': 'Nothing in progress right now.'}]
                   + [tab(c) for c in root['folders']])
    #a folder's own page: just what's in it, with tabs for the folders inside it
    if node:
        quiz_filter, shown = [tab(c) for c in node['folders']], under(node)
    #the last few handed in (any folder, any time), newest first, above the folders
    finished = sorted((cq for cq in current_user.cquizzes if cq.status in ('completed', 'review') and cq.compdate),
                      key=lambda cq: cq.compdate, reverse=True)[:LATEST_FINISHED]
    #the try that's due soon, by quiz (its badge says when)
    due_by_quiz = {cq.vquiz_id: cq for cq in waiting if cq.id in due_ids}
    #20 quizzes to a page (app/paging.py; the owner, 2026-10-23): the ones that still need the student first
    #(a try new or started, not only the latest), then the rest, each in the usual order (newest first)
    from app import paging
    ordered = [g for g in shown if g['open']] + [g for g in shown if not g['open']]
    rank = {'new': 3, 'started': 2, 'review': 2}
    pg = paging.paginate(ordered, name_of=lambda g: g['vquiz'].title or '', sorts={
        'title': lambda g: (g['vquiz'].title or '').lower(),
        'latest': lambda g: g['latest'].id,
        'attempts': lambda g: len(g['attempts']),
        'status': lambda g: max(rank.get(a.status, 1) for a in g['attempts']),
        'score': lambda g: g['combined']})
    shown = pg.items
    return render_template('mypage.html', current_user=current_user, student_rules=RETAKE_RULES_FOR_STUDENT, title='My quizzes',
                           due_by_quiz=due_by_quiz, pg=pg,
                           groups=groups, fk=fk, shown=shown, home=home, finished=finished,
                           showing=showing, nothing=nothing, quiz_filter=quiz_filter)


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
    #the same folder tab, when it's the same view (not one the action switched to)
    tab = kept_tab()
    if tab and str(show) == str(request.form.get('view') or 'main'):
        values['tab'] = tab
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
    return _folder_done('Folder “{}” made.'.format(f.name))  # stay where you were


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
    return _folder_done('Folder renamed to “{}”.'.format(f.name))


@user_bp.route('/mypage/folders/<int:folder_id>/delete', methods=['POST'])
@login_required
@pw_check
@post_form_only
def delete_folder(folder_id):
    from app.qgen import folders
    from app.qgen.models import QuizFolder, QuizPlacement, VQuiz
    from app import takeout
    f = db.session.get(QuizFolder, folder_id)
    mine = f is not None and f.owner_id == current_user.id
    parent = f.parent_id if mine else None
    #(what moves where, for the message: the quizzes and folders in it go up a level)
    up = db.session.get(QuizFolder, parent).name if parent else None
    quizzes = sorted('“{}”'.format(q.title) for q in VQuiz.query.join(QuizPlacement, QuizPlacement.vquiz_id == VQuiz.id)
                     .filter(QuizPlacement.owner_id == current_user.id, QuizPlacement.folder_id == folder_id)) if mine else []
    inner = sorted(g.name for g in QuizFolder.query.filter_by(owner_id=current_user.id, parent_id=folder_id)) if mine else []
    try:
        name = folders.delete_folder(current_user, folder_id)
    except folders.FolderError as exc:
        return _folder_done(str(exc), error=True)
    return _folder_done(takeout.moved_up_message(name, up, quizzes, inner),
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
    return _folder_done('Deleted the folder “{}”{}.'.format(
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
            where = '“{}”'.format(target.name) if target else 'the top'
            moved = 'folder:{}'.format(request.form.get('folder'))
        else:
            target = folders.move_quiz(current_user, request.form.get('quiz'), to)
            what = db.session.get(VQuiz, int(request.form.get('quiz'))).title
            where = '“{}”'.format(target.name) if target else 'Uncategorized'
            moved = 'quiz:{}'.format(request.form.get('quiz'))
    except folders.FolderError as exc:
        return _folder_done(str(exc), error=True)
    return _folder_done('Moved “{}” to {}.'.format(what, where), moved=moved)

#Home's "Just finished" (was "Recently completed"): how far back, and how many at most
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
    since = now - timedelta(days=tuning.get('recent_days'))
    recent = sorted((cq for cq in current_user.cquizzes if cq.status in ('completed', 'review') and cq.compdate and cq.compdate >= since),
                    key=lambda cq: cq.compdate, reverse=True)[:tuning.get('recent_max')]
    return render_template('home.html', title='Home', now=now, waiting=waiting, soon=soon, recent=recent, recent_days=tuning.get('recent_days'),
                           todo=sum(1 for cq in waiting if cq.status == 'new'),
                           started=sum(1 for cq in current_user.cquizzes if cq.status in ('started', 'review')),
                           awards=have, to_earn=awards.still_to_earn(current_user, have))

# route to user logout action
#(no password check: someone told to change their password can still log out, e.g. on a shared computer)
@user_bp.route('/logout')
@login_required
def logout():
    flash('You’re logged out.', 'success')
    current_app.logger.info('{} has logged out'.format(current_user.username))
    current_user.logged_in = False
    current_user.save()
    from app import push
    push.sign_out(current_user.id)
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
    from app.qgen.models import Setting
    return render_template('login.html', title='Log in', form=form, signup_open=bool(Setting.get('class_code')))

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
        flash('Your account “{}” is ready.'.format(form.username.data), 'success')
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
    #shown in a dialog with Copy and Done (base.html), not a message that goes away by itself
    #(the owner, 2026-10-16)
    flash({'name': usr.shown_name, 'password': pword}, 'temp-password')
    current_app.logger.info('{} issued a manual PW reset for {}'.format(current_user.username, usr.username))
    return redirect(back_to(url_for('user.userdet')))

# route to admin-initiated user deletion action
@user_bp.route('/deluser/<uid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def deluser(uid):
    #(archived or not: the Archive's People has Delete for good too)
    from .accounts import any_person
    usr = any_person(uid) if str(uid).isdigit() else None
    if usr is None:
        abort(404)
    usrname = usr.username
    if current_user == usr:
        flash("I can't let you do that, {}".format(current_user.shown_name))
        return redirect(url_for('user.userdet'))
    #their quiz attempts are kept in the archive
    from .accounts import delete_account
    delete_account(usr, by=current_user)
    flash('Deleted {}’s account.'.format(usrname), 'success')
    current_app.logger.info('{} deleted user: {}'.format(current_user.username, usrname))
    #back to the Users page they were on (its folder), not to the deleted person's pages
    users = url_for('user.userdet')
    back = back_to(users)
    return redirect(back if back.split('?')[0] == users else users)

#the trash can's Move to Archive for a person (the owner, 2026-10-16): they can't log in and
#leave every list; keep=yes keeps their quiz results and attempts, keep=no deletes them for good
@user_bp.route('/archiveuser/<int:uid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def archive_user(uid):
    from .accounts import any_person, archive_account
    usr = any_person(uid)
    if usr is None:
        abort(404)
    if usr == current_user:
        flash('You can’t move your own account to the Trash.', 'error')
        return redirect(url_for('user.userdet'))
    keep = request.form.get('keep') != 'no'
    archive_account(usr, by=current_user, keep_results=keep)
    flash(Markup('Moved {} to the <a href="{}">Trash</a>{}. You can restore him/her there.').format(
        usr.shown_name, url_for('qgen.archive', section='people'),
        '; his/her quiz results are kept' if keep else '; his/her quiz results were deleted'), 'success')
    current_app.logger.info('{} archived user {} ({} results)'.format(current_user.username, usr.username, 'kept' if keep else 'deleted'))
    users = url_for('user.userdet')
    back = back_to(users)
    return redirect(back if back.split('?')[0] == users else users)


@user_bp.route('/restoreuser/<int:uid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def restore_user(uid):
    from .accounts import any_person, restore_account
    usr = any_person(uid)
    if usr is None:
        abort(404)
    restore_account(usr)
    flash('{} is back; he/she can log in again.'.format(usr.shown_name), 'success')
    return redirect(url_for('qgen.archive', section='people'))

# route to admin-initiated user editing action
@user_bp.route('/edituser/<uid>', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def eduser(uid):
    uform = model_form(User, base_class=FlaskForm, db_session=db)
    uobj = User.query.filter_by(id=uid).first_or_404('No user with id {}'.format(uid))
    form = uform(obj=uobj)
    #(the site's word for them: the owner, 2026-10-20; the model's own label was "Is Admin")
    form.is_admin.label.text = 'Teacher'
    if request.method == 'POST':
        email = clean_email(form.email.data)
        taken = email and User.query.filter(User.email == email, User.id != uobj.id).first()
        if taken:
            flash('{} already uses that email address.'.format(taken.shown_name), 'error')
            return render_template('eduser.html', title='Edit user: {}'.format(uobj.shown_name), form=form)
        uobj.username = form.username.data
        uobj.email = email
        if uobj == current_user and uobj.is_admin != form.is_admin.data:
            flash('You can’t change whether you’re a teacher.', 'error')
        else:
            uobj.is_admin = form.is_admin.data
        uobj.save()
        flash('Updated user: ({}) {}'.format(uobj.id, uobj.shown_name))
        current_app.logger.info('{} updated user ({}) {}'.format(current_user.username, uobj.id, uobj.username))
        return redirect(next_arg(url_for('user.userdet')))
    return render_template('eduser.html', title='Edit user: {}'.format(uobj.shown_name), form=form)

# route to admin-initiated user detail listing
#People: everyone in the user folders, seen two ways: Accounts (this page: roles, last seen,
#editing) or Results (qgen.list_users: their quizzes and scores). The menu opens the one used last.
@user_bp.route('/people', methods=['GET'])
@login_required
@pw_check
@admin_only
def people():
    #(one People page: the owner, 2026-10-21; ?view= is ignored, the Results view is gone)
    args = request.args.to_dict()
    args.pop('view', None)
    return redirect(url_for('user.userdet', **args))


@user_bp.route('/userdet', methods=['GET'])
@login_required
@pw_check
@admin_only
def userdet():
    return people_page()


def people_page(in_archive=False, **extra):
    """People's Accounts view; in_archive: the Archive's People, the same page for the people
    moved to the Archive (Restore and Delete for good on each, the owner 2026-10-16)."""
    from . import groups
    from app import folder_tree
    if in_archive:
        from .accounts import archived_people
        ulst = sorted(archived_people(), key=lambda u: u.username)
        root, flat, nodes, folders_of = groups.tree(ulst, only={u.id for u in ulst})
    else:
        #(everyone's quizzes and their quizzes loaded together, not one person at a time: the People
        #page shows each person's results, the code critic 2026-10-22)
        from sqlalchemy.orm import selectinload
        from app.qgen.models import CQuiz
        ulst = User.query.options(selectinload(User.cquizzes).selectinload(CQuiz.vquiz)).order_by(User.username).all()
        root, flat, nodes, folders_of = groups.tree(ulst)
    #everyone (the default), the people in no folder ('main'), or a folder's id (a gone folder: everyone)
    view, node = folder_tree.view_of(folder_tree.choice_of(request.args), nodes, default='all')
    fk = folder_tree.kit(
        view, node, root, flat, nodes,
        page=(lambda v: url_for('qgen.archive', section='people', folder=v)) if in_archive else (lambda v: url_for('user.userdet', folder=v)),
        create_url=url_for('user.create_user_folder'), move_url=url_for('user.move_user_or_folder'),
        rename_url=lambda fid: url_for('user.rename_user_folder', folder_id=fid),
        delete_url=lambda fid: url_for('user.delete_user_folder', folder_id=fid),
        add_url=url_for('user.add_to_user_folder'), remove_url=url_for('user.remove_from_user_folder'),
        unit='person', units='people', all_label='All people', all_count=len(ulst), name=lambda f: f.name,
        placeholder='e.g. 7th grade', add_words='+', drag_what='a person',
        hint='Folders are shared by all teachers; students never see them. Someone can be in several folders.',
        #(no Assign paper plane at the top for a folder, Uncategorized or everyone: people are assigned from the
        #Checked folder's "Apply to checked", each person from his/her own row: the owner, 2026-10-24)
        fold_key='qgen-folded-user-folders')
    from app.qgen.models import RETAKE_RULES
    pg = _people_page_of(ulst, view, node, root, in_archive)
    return render_template('udet.html', ulst=ulst, title='Trash' if in_archive else 'People', fk=fk, shown=pg.items, pg=pg,
                           folders_of=folders_of, in_archive=in_archive, rules=RETAKE_RULES, **extra)


def _people_page_of(ulst, view, node, root, in_archive):
    """The people to draw: the folder shown (or what's checked, ?checked=), narrowed by the words
    typed (?q=) and People's Show choice (?state=review or out: someone with an attempt waiting for
    grading, or not handed in yet), sorted (?sort=), 20 to the page (app/paging.py; the owner,
    2026-10-23)."""
    from app import folder_tree, paging
    from app.qgen.models import attempts_by_quiz
    checked = request.args.get('checked')
    if checked is not None:
        want = {x for x in checked.split(',') if x}
        listed = [u for u in ulst if str(u.id) in want]
    elif view == 'all':
        listed = ulst
    elif view == 'main':
        listed = root['people']
    else:
        listed = folder_tree.subtree(node)
    sums = {}

    def facts(u):
        #(what each column says, worked out once: the same numbers the row shows)
        if u.id not in sums:
            groups = attempts_by_quiz(u.cquizzes) if not in_archive else []
            done = [g['combined'] for g in groups if g['combined'] is not None]
            sums[u.id] = {
                'states': {'review' if any(a.status == 'review' for a in g['attempts']) else 'out' if g['open'] else 'done' for g in groups},
                'quizzes': len({c.vquiz_id for c in u.cquizzes}) if not in_archive else 0,
                'going': sum(1 for c in u.cquizzes if c.status in ('started', 'review')) if not in_archive else 0,
                'fresh': sum(1 for c in u.cquizzes if c.status == 'new') if not in_archive else 0,
                'avg': sum(float(x) for x in done) / len(done) if done else None}
        return sums[u.id]
    state = request.args.get('state')
    if state in ('review', 'out') and not in_archive:
        listed = [u for u in listed if state in facts(u)['states']]
    sorts = {'name': lambda u: u.username.lower(),
             'created': lambda u: u.created_at,
             'quizzes': lambda u: facts(u)['quizzes'],
             'status': lambda u: (facts(u)['going'], facts(u)['fresh']) if facts(u)['going'] or facts(u)['fresh'] else None,
             'average': lambda u: facts(u)['avg'],
             'done': lambda u: facts(u)['avg']}  # (an old address's ?sort=done: the same as Average)
    pg = paging.paginate(listed, name_of=lambda u: u.username + ' ' + (u.nickname or ''), sorts=sorts, show=request.args.get('show'))
    if checked is not None:
        pg.label, pg.icon = 'Checked', 'lc-folder-check'
    return pg


def _assign_all_button(people, label, title, empty):
    # People's All and Uncategorized tabs: Assign with those people checked (grayed when there are none)
    #(the paper plane, like every Assign: the owner, 2026-10-14)
    if not people:
        return Markup('<button type="button" class="btn btn-secondary btn-xs btn-icon" disabled title="{}">{}</button> ').format(empty, icon_label('lc-send', label))
    return Markup('<a class="btn btn-secondary btn-xs btn-icon" href="{}" title="{}">{}</a> ').format(
        url_for('qgen.assign', users=[u.id for u in people]), title, icon_label('lc-send', label))


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
    values = {'folder': show} if show.isdigit() or show in ('main', 'all') else {}
    #the same folder tab, when it's the same view (not one the action switched to)
    tab = kept_tab()
    if tab and str(show) == str(request.form.get('view') or 'main'):
        values['tab'] = tab
    if moved and not error:
        values['moved'] = moved  # lit up on the page, like after a drag
    from app.qgen.routes import from_archive
    if from_archive():
        return redirect(url_for('qgen.archive', section='people', **values))
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
    return _group_done('Folder “{}” made.'.format(f.name))  # stay where you were


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
    return _group_done('Folder renamed to “{}”.'.format(f.name))


@user_bp.route('/users/folders/<int:folder_id>/delete', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delete_user_folder(folder_id):
    from . import groups
    from .models import UserFolder
    from app import takeout
    f = db.session.get(UserFolder, folder_id)
    parent = f.parent_id if f is not None else None
    said = takeout.folder_delete_plan('people', f) if f is not None else None  # (who moves where)
    try:
        groups.remove(folder_id)
    except groups.GroupError as exc:
        return _group_done(str(exc), error=True)
    return _group_done(said(),
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
            message = 'Moved “{}” to {}.'.format(name, '“{}”'.format(target.name) if target else 'the top level')
        elif to in (None, '', 'top', 'main'):
            #(from the All list, like the Problems and Quizzes pages: which folder isn't known)
            if here is None:
                return _group_done('Drag them out of a folder to take them out (or use the ✕ on the folder).', error=True)
            #left in no folder: deleted, asked first (app/takeout.py)
            from app import takeout
            return takeout.handle('people', [request.form.get('user')], here, lambda m, error=False: _group_done(m, error=error))
        else:
            person, f = groups.add(request.form.get('user'), to, moving_from=here)
            message = 'Moved {} to “{}”.'.format(person.shown_name, f.name) if here else \
                'Put {} in “{}”.'.format(person.shown_name, f.name)
    except groups.GroupError as exc:
        return _group_done(str(exc), error=True)
    return _group_done(message, moved='folder:{}'.format(request.form.get('folder')) if request.form.get('folder')
                       else 'user:{}'.format(request.form.get('user')))


#route for People's checked bar: put everyone checked in the folder chosen, or take them out of
#it (the same as the Problems and Quizzes pages' bar; out of their only folder: asked first)
@user_bp.route('/users/folders/file', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def file_people():
    from . import groups
    from app import takeout
    people, folder = request.form.getlist('items'), request.form.get('folder')
    if not people:
        return _group_done('Check at least one first.', error=True)
    if request.form.get('action') == 'remove' and folder == 'own':
        return takeout.handle_each('people', people, lambda m, error=False: _group_done(m, error=error))
    if request.form.get('action') == 'remove':
        return takeout.handle('people', people, folder, lambda m, error=False: _group_done(m, error=error), one_folder=True)
    #(one folder or several: the Put in folder dialog lets several be checked, the owner 2026-10-15)
    folders = list(dict.fromkeys(f for f in request.form.getlist('folder') if f))
    #(moving, the dialog's usual way: into one folder, out of the others, the owner 2026-10-16)
    if request.form.get('action') == 'move':
        if len(folders) != 1:
            return _group_done('Choose one folder to move to.', error=True)
        try:
            names = []
            for uid in dict.fromkeys(people):
                if request.form.get('from'):
                    #("Move from “X”", from a card's Remove: out of that folder only)
                    person, f = groups.add(uid, folders[0], moving_from=request.form.get('from'))
                else:
                    person, f = groups.move_to(uid, folders[0])
                names.append(person.shown_name)
        except groups.GroupError as exc:
            return _group_done(str(exc), error=True)
        return _group_done('Moved {} to “{}”.'.format(', '.join(names), f.name))
    try:
        names, where = [], []
        for fid in folders:
            for uid in dict.fromkeys(people):
                person, f = groups.add(uid, fid)
                if person.shown_name not in names:
                    names.append(person.shown_name)
            where.append('“{}”'.format(f.name))
    except groups.GroupError as exc:
        return _group_done(str(exc), error=True)
    if not where:
        return _group_done('Choose a folder first.', error=True)
    return _group_done('Put {} in {}.'.format(', '.join(names), ' and '.join(where)))


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
    return _group_done('Put {} in “{}”.'.format(person.shown_name, f.name), moved='user:{}'.format(person.id))


@user_bp.route('/users/folders/remove', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def remove_from_user_folder():
    #just that folder; left in no folder: deleted, asked first (app/takeout.py)
    from app import takeout
    return takeout.handle('people', [request.form.get('user')], request.form.get('folder'),
                          lambda m, error=False: _group_done(m, error=error), one_folder=True)

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
        flash('Settings saved. ' + ('Students can sign up with the class code “{}”.'.format(code) if code
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
            flash('“{}” is back to its default.'.format(tuning.BY_KEY[key]['label']), 'success')
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
    flash('Your nickname is now “{}”.'.format(nick) if nick else 'Your nickname is gone; your name shows on its own.', 'success')
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
        flash('Token “{}” revoked: apps using it are signed out.'.format(row.name), 'success')
    return redirect(url_for('user.profile'))
