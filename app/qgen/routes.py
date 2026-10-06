from . import db, qgen_bp
from app.user.models import User
from app.user.routes import admin_only, pw_check
from app.home import home_url
from .formfact import quiz_form_class, quiz_items, form_answers, transcript_html, transcript_item, fieldname_base
from . import services as S
from .forms import ProblemForm, QuizForm, AssignForm, ReviewForm
from .models import CQuiz, VQuiz, VProblem, ArchivedAttempt, RETAKE_RULES
from .qtypes import get_qtype, REGISTRY
from .friendly import KINDS, FriendlyError
from . import layout
from flask import flash, render_template, redirect, url_for, request, current_app, abort, jsonify
from app.nav import back_to, safe_next, next_arg, place_name
from markupsafe import Markup
from app.jsoncsrf import json_csrf_ok, post_form_only
from flask_login import current_user, login_required
from datetime import datetime, timedelta
import json

def parse_vplist(text):
    """The quiz's problem list from the form: single ids and groups."""
    return layout.parse(text)


# ---------------------------------------------------------------- subjects

LIST_PAGES = {'problems': 'qgen.list_vprobs', 'quizzes': 'qgen.list_vquizzes'}


def ticked_subjects(item, rel):
    """The subject ids checked on an edit form (as sent, or as saved)."""
    if request.method == 'POST':
        return {int(i) for i in request.form.getlist('subjects') if i.isdigit()}
    return {g.id for g in getattr(item, rel)} if item is not None else set()


def subject_form_error(kind, new):
    """The Subjects question on the edit forms: a new problem (quiz) must go in a subject,
    in a new one typed there, or in Unsorted. None when it's answered."""
    if not request.form.get('subjects_shown'):
        return None
    name = request.form.get('new_subject', '')
    error = S.new_subject_name_error(kind, name)
    if error:
        return error
    chosen = [i for i in request.form.getlist('subjects') if S.get_subject(kind, i)]
    if new and not (chosen or name.strip() or request.form.get('unsorted')):
        return 'Choose a folder for this {}, or Not in a folder to file it later.'.format('problem' if kind == 'problems' else 'quiz')
    return None


def save_subjects(kind, item):
    """File the item as checked on its form (only forms that show the Subjects row)."""
    if request.form.get('subjects_shown'):
        S.set_subjects(kind, item, request.form.getlist('subjects'))
        db.session.commit()
        name = request.form.get('new_subject', '')
        if name.strip():
            S.file_items(kind, [item.id], S.subject_named(kind, name))


def subject_page_data(kind, item=None, rel=None, error=None):
    return {'subject_kind': kind, 'all_subjects': S.subject_tree(kind, items=[])[1],
            'ticked_subjects': ticked_subjects(item, rel) if rel else set(),
            'subject_error': error, 'new_item': item is None or item.id is None,
            'unsorted_ticked': bool(request.form.get('unsorted')) if request.method == 'POST' else False,
            'new_subject_name': request.form.get('new_subject', '') if request.method == 'POST' else ''}


# ---------------------------------------------------------------- problems

def problem_page(form, vp, errors, title, subject_error=None):
    #unbound copy with one empty row of each kind, cloned by problem_form.js for "+ Add"
    blank = ProblemForm(formdata=None)
    blank.values.append_entry()
    blank.images.append_entry()
    return render_template('problem_form.html', form=form, vp=vp, errors=errors, title=title, blank=blank,
                           kinds=KINDS, qtypes=REGISTRY, ai_enabled=bool(current_app.config.get('ANTHROPIC_API_KEY')),
                           **subject_page_data('problems', vp, 'vpgroups', subject_error))

def save_from_form(form, vp):
    return S.save_problem(vp, form.qtype.data, form.title.data, form.question.data, form.answer.data,
                          form.options(), form.calculator_ok.data)

#route to create a virtual problem
@qgen_bp.route('/quiz/makevprob', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def mkvprob():
    form = ProblemForm()
    errors, subject_error = [], None
    if form.validate_on_submit():
        nuprob = VProblem(author_id=current_user.id)
        subject_error = subject_form_error('problems', new=True)
        errors = [subject_error] if subject_error else save_from_form(form, nuprob)
        if not errors:
            save_subjects('problems', nuprob)
            flash('Saved problem "{}".'.format(nuprob.title), 'success')
            current_app.logger.info('{} created VProblem: ({}) "{}"'.format(current_user.username, nuprob.id, nuprob.title))
            return redirect(url_for('qgen.list_vprobs', show=nuprob.id))
    elif request.method == 'GET' and not form.values.entries:
        form.values.append_entry()
    return problem_page(form, None, errors, 'New problem', subject_error)

#route to view a problem as students get it (three sample versions), without editing
@qgen_bp.route('/quiz/viewvprob/<vpid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def view_vprob(vpid):
    vp = db.get_or_404(VProblem, vpid)
    try:
        samples, error = S.sample_problem(vp), None
    except S.ServiceError as exc:
        samples, error = [], str(exc)
    return render_template('view_problem.html', vp=vp, qt=get_qtype(vp.qtype), samples=samples, error=error,
                           title='View: {}'.format(vp.title))

#route to edit a specific virtual problem
@qgen_bp.route('/quiz/editvprob/<vpid>', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def edvprob(vpid):
    vpobj = VProblem.query.filter_by(id=vpid).first_or_404('No vproblem with id {}'.format(vpid))
    form = ProblemForm()
    errors, subject_error = [], None
    if request.method == 'GET':
        form.load(vpobj)
    elif form.validate_on_submit():
        subject_error = subject_form_error('problems', new=False)
        errors = [subject_error] if subject_error else save_from_form(form, vpobj)
        if not errors:
            save_subjects('problems', vpobj)
            flash('Updated problem "{}". Quizzes already assigned keep the version they were given.'.format(vpobj.title), 'success')
            current_app.logger.info('{} updated VProblem: ({}) "{}"'.format(current_user.username, vpobj.id, vpobj.title))
            return redirect(next_arg(url_for('qgen.list_vprobs', show=vpobj.id)))
    return problem_page(form, vpobj, errors, 'Edit problem', subject_error)

#"Show me 3 examples": run the problem without saving it
@qgen_bp.route('/quiz/previewvprob', methods=['POST'])
@login_required
@pw_check
@admin_only
def preview_vprob():
    form = ProblemForm()
    if not form.validate_on_submit() and 'csrf_token' in form.errors:
        return render_template('_preview.html', errors=['Your session expired. Please reload the page.'])
    errors, samples = S.preview_problem(form.qtype.data, form.question.data, form.answer.data, form.options())
    return render_template('_preview.html', errors=errors, samples=samples, essay=not get_qtype(form.qtype.data).auto_graded)

#route to list all virtual problems
@qgen_bp.route('/quiz/listvp', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vprobs():
    return subject_page('problems', 'vplist.html', qtypes=REGISTRY, title='Problems', all_subjects=S.subject_tree('problems')[1],
                        archived=S.archived_counts()[1], archive_warning=S.archive_warning)

#route to list a specific virtual problem
@qgen_bp.route('/quiz/listvp/<vpid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vprob(vpid):
    vplst = VProblem.query.filter_by(id=vpid).first_or_404('No vproblem with id {}'.format(vpid))
    return render_template('vplist.html', boxes=None, items=[vplst], total=1, qtypes=REGISTRY, title=vplst.title or 'Untitled problem',
                           kind='problems', single=True, archived=S.archived_counts()[1], archive_warning=S.archive_warning)

#route to delete a specific virtual problem
@qgen_bp.route('/quiz/delvp/<vpid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def del_vprob(vpid):
    vp = VProblem.query.filter_by(id=vpid).first_or_404('No VProblem with id {}'.format(vpid))
    title = vp.title
    try:
        S.delete_problem(vp)
    except S.ServiceError as exc:
        flash('Not deleted. {}'.format(exc), 'error')
        return redirect(url_for('qgen.list_vprobs'))
    flash('Deleted problem "{}".'.format(title), 'success')
    current_app.logger.info("{} deleted VProblem: ({}) '{}'".format(current_user.username, vpid, title))
    return redirect(url_for('qgen.list_vprobs'))


# ---------------------------------------------------------------- quizzes

def quiz_page(form, title, vq=None, subject_error=None):
    return render_template('quiz_form.html', form=form, title=title, problem_boxes=S.subject_boxes('problems'), problem_paths=S.subject_paths('problems'),
                           has_problems=VProblem.query.count() > 0, qtypes=REGISTRY, vq=vq,
                           ai_enabled=bool(current_app.config.get('ANTHROPIC_API_KEY')),
                           retake_overrides=S.retake_overrides(vq) if vq is not None and vq.id else [],
                           rules=RETAKE_RULES, **subject_page_data('quizzes', vq, 'vqgroups', subject_error))

def save_quiz_from_form(form, vq):
    errors = S.save_vquiz(vq, form.title.data, form.vplist.data, author_id=current_user.id,
                          image=form.image.data or None, calculator_ok=form.calculator_ok.data,
                          shuffle_order=form.shuffle_order.data, retake_rule=form.retake_rule.data)
    form.vplist.errors = errors
    return errors

#route to create a virtual quiz
@qgen_bp.route('/quiz/makevquiz', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def mkvquiz():
    form = QuizForm()
    subject_error = None
    if form.validate_on_submit():
        nq = VQuiz()
        subject_error = subject_form_error('quizzes', new=True)
        if not subject_error and not save_quiz_from_form(form, nq):
            save_subjects('quizzes', nq)
            count = layout.question_count(layout.parse(nq.vpid_lst))
            flash('Created quiz "{}": each student gets {} question{}.'.format(nq.title, count, '' if count == 1 else 's'), 'success')
            current_app.logger.info('{} created VQuiz: ({}) "{}"'.format(current_user.username, nq.id, nq.title))
            return redirect(url_for('qgen.list_vquizzes', show=nq.id))
    return quiz_page(form, 'New quiz', subject_error=subject_error)

#route to view a quiz as one student would get it, without editing or assigning
@qgen_bp.route('/quiz/viewvquiz/<vqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def view_vquiz(vqid):
    vq = db.get_or_404(VQuiz, vqid)
    try:
        items, error = S.sample_quiz(vq), None
    except S.ServiceError as exc:
        items, error = [], str(exc)
    return render_template('view_quiz.html', vq=vq, items=items, error=error, title='View: {}'.format(vq.title))

#route to edit a specific virtual quiz
@qgen_bp.route('/quiz/editvquiz/<vqid>', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def edvquiz(vqid):
    vqobj = VQuiz.query.filter_by(id=vqid).first() if str(vqid).isdigit() else None
    if vqobj is None:
        return gone('That quiz has been deleted.', url_for('qgen.list_vquizzes'))
    form = QuizForm(obj=vqobj)
    if request.method == 'GET':
        form.vplist.data = layout.dumps(layout.parse(vqobj.vpid_lst))
    subject_error = None
    if request.method == 'POST' and form.validate_on_submit():
        subject_error = subject_form_error('quizzes', new=False)
        old_rule, had_own = vqobj.retake_rule, len(S.retake_overrides(vqobj))
        if not subject_error and not save_quiz_from_form(form, vqobj):
            save_subjects('quizzes', vqobj)
            flash('Updated quiz "{}". Quizzes already assigned keep the version they were given.'.format(vqobj.title), 'success')
            if vqobj.retake_rule != old_rule and had_own:
                flash('The new retake scoring now applies to every student, including the {} who had their own.'.format(
                    'one' if had_own == 1 else had_own), 'success')
            current_app.logger.info('{} updated VQuiz: ({}) "{}"'.format(current_user.username, vqobj.id, vqobj.title))
            return redirect(next_arg(url_for('qgen.list_vquizzes', show=vqobj.id)))
    return quiz_page(form, 'Edit quiz', vqobj, subject_error)

#route to list all virtual quizzes
@qgen_bp.route('/quiz/listvq', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vquizzes():
    return subject_page('quizzes', 'vqlist.html', title='Quizzes', layout=layout, rules=RETAKE_RULES,
                        all_subjects=S.subject_tree('quizzes')[1], archived=S.archived_counts()[0], archive_warning=S.archive_warning)

#route to list a specific virtual quiz
@qgen_bp.route('/quiz/listvq/<vqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vquiz(vqid):
    vqlst = VQuiz.query.filter_by(id=vqid).first() if str(vqid).isdigit() else None
    if vqlst is None:
        return gone('That quiz has been deleted.', url_for('qgen.list_vquizzes'))
    return render_template('vqlist.html', boxes=None, items=[vqlst], total=1, title=vqlst.title or 'Untitled quiz', layout=layout, rules=RETAKE_RULES,
                           kind='quizzes', single=True, archived=S.archived_counts()[0], archive_warning=S.archive_warning)

#route to delete a specific virtual quiz
@qgen_bp.route('/quiz/delvq/<vqid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def del_vquiz(vqid):
    vq = VQuiz.query.filter_by(id=vqid).first_or_404('No VQuiz with id {}'.format(vqid))
    title = vq.title
    try:
        S.delete_vquiz(vq)
    except S.ServiceError as exc:
        flash('Not deleted. {}'.format(exc), 'error')
        return redirect(url_for('qgen.list_vquizzes'))
    flash('Deleted quiz "{}".'.format(title), 'success')
    current_app.logger.info("{} deleted VQuiz: ({}) '{}'".format(current_user.username, vqid, title))
    return redirect(url_for('qgen.list_vquizzes'))


#route to set how one student's attempts at one quiz combine ('' = use the quiz's rule)
@qgen_bp.route('/quiz/retakerule/<cqid>', methods=['POST'])
@login_required
@pw_check
@admin_only
def set_retake_rule(cqid):
    from .models import RETAKE_RULES
    cq = db.get_or_404(CQuiz, cqid)
    rule = request.form.get('rule') or None
    try:
        S.set_retake_rule(cq, rule)
    except S.ServiceError:
        abort(400)
    flash('{}\'s score for "{}" is now: {}.'.format(cq.taker.shown_name, cq.vquiz.title,
          RETAKE_RULES[rule].lower() if rule else 'the quiz\'s own rule'), 'success')
    return redirect(back_to(url_for('qgen.list_user', uid=cq.assignee)))


# ---------------------------------------------------------------- assigning

#route to assign a concrete quiz to one or more users
@qgen_bp.route('/quiz/assign', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def assign():
    form = AssignForm()
    quizzes = VQuiz.query.order_by(VQuiz.title).all()
    form.vquiz.choices = [(q.id, q.title) for q in quizzes]
    form.users.choices = [(u.id, u.username) for u in User.query.order_by(User.username).all()]
    #a link for one quiz opens on All, so that quiz is in the list
    choice = 'all' if request.args.get('vq', '').isdigit() else S.valid_subject_choice('quizzes', request.args.get('subject', 'all'))
    if request.method == 'GET' and request.args.get('vq', '').isdigit():
        form.vquiz.data = int(request.args['vq'])
    if form.validate_on_submit():
        vquiz = db.get_or_404(VQuiz, form.vquiz.data)
        #each person once, however many folders they were checked in
        students = [db.session.get(User, uid) for uid in dict.fromkeys(form.users.data)]
        created, failed = S.assign(vquiz, [u for u in students if u], form.opens_at.data, form.closes_at.data, form.time_limit.data,
                                   by=current_user)
        for student, err in failed:
            flash(err, 'error')
            current_app.logger.error(err)
        for cq in created:
            current_app.logger.info('{} assigned quiz: "{}" ({}) to {}'.format(current_user.username, vquiz.title, cq.id, cq.taker.username))
        if created:
            flash(Markup('Assigned “{}” to {}. <a href="{}">See the results →</a>').format(
                vquiz.title, ', '.join(cq.taker.shown_name for cq in created), url_for('qgen.quiz_results_page', vqid=vquiz.id)), 'success')
        #back where they came from (a student page, a quiz's results...), else ready for the next one
        return redirect(next_arg(url_for('qgen.assign')))
    #for the Subject menu, which narrows the Quiz menu in the page
    #a quiz in "Algebra › Linear equations" is also under "Algebra"
    above = S.subject_ancestors('quizzes')
    quiz_subjects = {q.id: sorted({a for g in q.vqgroups for a in above.get(g.id, [g.id])}) for q in quizzes}
    #a quiz really chosen (from a link, or sent back after a form error) is kept on show
    quiz_chosen = request.method == 'POST' or request.args.get('vq', '').isdigit()
    #the people to choose from, in the Users page's folders; from the Users page, some come
    #already checked (?users=..., or everyone in ?folder=), with their folder open
    from app.user import groups
    people = User.query.order_by(User.username).all()
    root, _, nodes, folders_of = groups.tree(people)
    chosen, open_groups = set(form.users.data or []), set()
    if request.method == 'GET':
        chosen = {int(u) for u in request.args.getlist('users') if u.isdigit()} & {u.id for u in people}
        folder = request.args.get('folder', '')
        def show(f):  # open a folder and the ones it's in
            while f is not None:
                open_groups.add(f.id)
                f = nodes[f.parent_id]['folder'] if f.parent_id in nodes else None
        if folder.isdigit() and int(folder) in nodes:
            chosen |= nodes[int(folder)]['everyone']
            show(nodes[int(folder)]['folder'])
        else:
            #people named one by one: open where each of them is
            for uid in chosen:
                for f in folders_of.get(uid, []):
                    show(f)
                if uid not in folders_of:
                    open_groups.add('none' if root['folders'] else 'all')
    #the page they came from, when it's one to go back to (the Assign page itself isn't)
    from app.nav import back
    target = request.form.get('next') if request.method == 'POST' else None
    came_from = back(None, None) if not target else (safe_next(target), place_name(safe_next(target)))
    came_from = came_from if came_from and came_from[0] and came_from[1] else None
    return render_template('assign.html', title='Assign a quiz', form=form, came_from=came_from, choices=S.subject_choices('quizzes'),
                           choice=choice, quiz_subjects=quiz_subjects, quiz_chosen=quiz_chosen,
                           people=people, root=root, chosen=chosen, open_groups=open_groups)


# ---------------------------------------------------------------- taking

def prefill(cq, form):
    """Put autosaved answers back into the quiz form."""
    for cp in cq.cproblems:
        if cp.submitted is None:
            continue
        field = form[fieldname_base.format(cp.ordinal)]
        qt = get_qtype(cp.vproblem.qtype)
        if qt.uses_choices or qt.key == 'truefalse':
            picked = [str(i) for i in qt.picked(cp.submitted)]
            field.data = picked if qt.multi else (picked[0] if picked else None)
        else:
            field.data = cp.submitted

#route for an assigned user to begin taking a concrete quiz
@qgen_bp.route('/quiz/take/<cidx>', methods=['GET','POST'])
@login_required
@pw_check
def qtake(cidx):
    cq = CQuiz.query.filter_by(id=cidx).first()
    if cq is None:
        return attempt_gone(cidx)
    if not cq.taker:
        flash('That quiz is not assigned to anyone.', 'error')
        return redirect(home_url())
    if current_user != cq.taker and not current_user.is_admin:
        flash('That quiz belongs to someone else.', 'error')
        return redirect(url_for('user.mypage'))
    title = cq.vquiz.title
    is_taker = current_user == cq.taker
    #opened from Home or a notice: no longer new (the count beside "My quizzes" goes down)
    if is_taker and not cq.seen_by_taker:
        cq.seen_by_taker = True
        db.session.commit()
    state = S.attempt_state(cq)
    #handed in: the taker is offered what's next
    from .models import next_quiz
    up_next = next_quiz(current_user, cq) if is_taker else None
    if state == 'completed':
        return render_template('transcript.html', cq=cq, title=title, transcript=transcript_html(cq, title), up_next=up_next)
    if state == 'review':
        return render_template('awaiting.html', cq=cq, title=title, up_next=up_next)
    if state == 'not_open' and is_taker:
        return render_template('not_open.html', cq=cq, title=title)
    #out of time: close it with whatever was autosaved
    if state == 'time_up' and is_taker:
        S.submit(cq)
        flash('Time ran out, so your answers were handed in.', 'info')
        current_app.logger.info('{} ran out of time on "{}" ({})'.format(current_user.username, title, cidx))
        return redirect(url_for('qgen.qtake', cidx=cidx))
    form = quiz_form_class(cq)()
    if is_taker:
        if form.validate_on_submit():
            S.submit(cq, form_answers(cq, form))
            current_app.logger.info('{} submitted "{}" ({})'.format(current_user.username, title, cidx))
            return redirect(url_for('qgen.qtake', cidx=cidx))
        if not cq.startdate:
            S.start(cq)
            current_app.logger.info('{} is starting "{}" ({})'.format(current_user.username, title, cidx))
    elif request.method == 'POST':
        flash("Only {} can submit this quiz.".format(cq.taker.shown_name), 'error')
    if request.method == 'GET':
        prefill(cq, form)
    return render_template('quiz_take.html', cq=cq, form=form, items=quiz_items(cq, form), title=title,
                           preview=not is_taker, deadline=cq.deadline())

#autosave: the quiz page sends the answers so far every few seconds
@qgen_bp.route('/quiz/take/<cidx>/save', methods=['POST'])
@login_required
@pw_check
def qsave(cidx):
    cq = CQuiz.query.filter_by(id=cidx).first()
    if cq is None:
        if archived_for(cidx):
            return jsonify(ok=False, error='Your teacher has taken this quiz away.'), 410
        abort(404)
    if current_user != cq.taker:
        return jsonify(ok=False, error='Not your quiz.'), 403
    if not json_csrf_ok():
        return jsonify(ok=False, error='Your session expired. Please reload the page.'), 400
    form = quiz_form_class(cq)(meta={'csrf': False})
    #only questions the page sent (a question with nothing checked sends just its marker)
    sent = {cp.ordinal: form[fieldname_base.format(cp.ordinal)].data for cp in cq.cproblems
            if fieldname_base.format(cp.ordinal) in request.form or fieldname_base.format(cp.ordinal) + '_present' in request.form}
    try:
        S.autosave(cq, sent)
    except S.ServiceError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    return jsonify(ok=True, saved=datetime.now().strftime('%I:%M:%S %p').lstrip('0'))


# ---------------------------------------------------------------- review

def waiting_for_grading():
    """Attempts waiting for grading, oldest hand-in first (the Grading list's order)."""
    return CQuiz.query.filter_by(needs_review=True, completed=False).order_by(CQuiz.compdate, CQuiz.id).all()

#route to list quizzes waiting for an instructor
@qgen_bp.route('/quiz/review', methods=['GET'])
@login_required
@pw_check
@admin_only
def review_list():
    waiting = waiting_for_grading()
    return render_template('review_list.html', waiting=waiting, title='Grading')

#route to grade the essay answers of one quiz
@qgen_bp.route('/quiz/review/<cqid>', methods=['GET', 'POST'])
@login_required
@pw_check
@admin_only
def review(cqid):
    cq = CQuiz.query.filter_by(id=cqid).first() if str(cqid).isdigit() else None
    if cq is None:
        return attempt_gone(cqid)
    if cq.completed:
        flash('That quiz has already been graded.', 'info')
        return redirect(url_for('qgen.qtake', cidx=cq.id))
    if not cq.needs_review:
        flash("That quiz hasn't been submitted yet.", 'info')
        return redirect(url_for('qgen.review_list'))
    form = ReviewForm()
    if request.method == 'GET':
        for cp in S.essays(cq):
            form.items.append_entry(dict(cpid=cp.id, credit=None if cp.credit is None else round(cp.credit * 100),
                                         feedback=cp.feedback or '', highlights=cp.highlights_json or '[]'))
    elif form.validate_on_submit():
        grades = {}
        for item in form.items.data:
            try:
                spans = json.loads(item['highlights'] or '[]')
            except ValueError:
                spans = []
            grades[int(item['cpid'] or 0)] = {'credit': item['credit'], 'feedback': item['feedback'], 'highlights': spans}
        try:
            finish = bool(form.finalize.data or form.finalize_next.data)
            ungraded = S.grade_essays(cq, grades, finish=finish, grader_id=current_user.id)
        except S.ServiceError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('qgen.review', cqid=cq.id))
        if ungraded:
            flash('Give a credit for question{} {} before finishing.'.format('s' if len(ungraded) > 1 else '', ', '.join(map(str, ungraded))), 'error')
            return redirect(url_for('qgen.review', cqid=cq.id))
        if finish:
            flash('Finished grading {}\'s "{}": {:.0f}%.'.format(cq.taker.shown_name, cq.vquiz.title, cq.score), 'success')
            current_app.logger.info('{} graded CQuiz ({}) for {}'.format(current_user.username, cq.id, cq.taker.username))
            after = waiting_for_grading()
            if form.finalize_next.data and after:
                return redirect(url_for('qgen.review', cqid=after[0].id))
            if form.finalize_next.data:
                flash('That was the last one: nothing else is waiting for grading.', 'success')
            return redirect(url_for('qgen.review_list'))
        flash('Draft saved.', 'success')
        return redirect(url_for('qgen.review', cqid=cq.id))
    entries = {int(e.form.cpid.data): e.form for e in form.items}
    items = [dict(item=transcript_item(cp), cp=cp, form=entries.get(cp.id),
                  notes=cp.vproblem.options.get('grading_notes'), raw=cp.submitted or '')
             for cp in cq.cproblems]
    queue = waiting_for_grading()
    place = next((i for i, w in enumerate(queue) if w.id == cq.id), None)
    return render_template('review.html', cq=cq, form=form, items=items, queue=queue, place=place,
                           others=len([w for w in queue if w.id != cq.id]), title='Grade: {} – {}'.format(cq.taker.username, cq.vquiz.title))


# ---------------------------------------------------------------- students

#route to list users
@qgen_bp.route('/quiz/listuser', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_users():
    """Results by student, in the Users page's folders: ?folder= all (the default), main (in
    no folder) or a folder's id."""
    from app import folder_tree
    from app.user import groups
    from .models import RETAKE_RULES
    ulst = User.query.order_by(User.username).all()
    root, flat, nodes, _folders_of = groups.tree(ulst)
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='all')
    shown = node['people'] if node else ulst if view == 'all' else root['people']
    fk = folder_tree.kit(
        view, node, root, flat, nodes, readonly=True,
        page=lambda v: url_for('qgen.list_users', folder=v) if str(v) != 'all' else url_for('qgen.list_users'),
        unit='person', units='people', all_label='Everyone', all_count=len(ulst), name=lambda f: f.name,
        hint=Markup('The <a href="{}">Users page</a>\'s folders: make and fill them there.').format(url_for('user.userdet')),
        fold_key='qgen-folded-results-student-folders', open_key='qgen-open-results-student-subfolders',
        item_key='qgen-open-results-students')
    return render_template('ulist.html', ulst=ulst, shown=shown, fk=fk, rules=RETAKE_RULES, title='Results by student',
                           find_label='Find a student or quiz…')

#route to list a specific user
@qgen_bp.route('/quiz/listuser/<uid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_user(uid):
    ulst = User.query.filter_by(id=uid).first() if str(uid).isdigit() else None
    if ulst is None:
        return gone("That person's account has been deleted.", url_for('user.userdet'))
    from .models import RETAKE_RULES
    from . import awards
    return render_template('ulist.html', ulst=[ulst], rules=RETAKE_RULES, single=True, title="{}'s quizzes".format(ulst.shown_name),
                           awards=awards.earned(ulst))

#Results by quiz: each quiz with its students' attempts (the other way round from Results by student)
@qgen_bp.route('/quiz/results', methods=['GET'])
@login_required
@pw_check
@admin_only
def results_by_quiz():
    from app import folder_tree
    from .models import RETAKE_RULES
    quizzes = VQuiz.query.order_by(VQuiz.title).all()
    root, flat, nodes = S.subject_tree('quizzes', items=quizzes)
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='all')
    shown = node['items'] if node else quizzes if view == 'all' else root['items']
    #each quiz's results, worked out once even if it's in several folders
    results = {q['vquiz'].id: q for q in quiz_results(quizzes)}
    fk = folder_tree.kit(
        view, node, root, flat, nodes, readonly=True,
        page=lambda v: url_for('qgen.results_by_quiz', folder=v) if str(v) != 'all' else url_for('qgen.results_by_quiz'),
        unit='quiz', units='quizzes', all_label='All quizzes', all_count=len(quizzes), name=lambda f: f.title,
        hint=Markup('The <a href="{}">Quizzes page</a>\'s folders: make and fill them there.').format(url_for('qgen.list_vquizzes')),
        fold_key='qgen-folded-results-quiz-folders', open_key='qgen-open-results-quiz-subfolders',
        item_key='qgen-open-results-quizzes')
    return render_template('results_by_quiz.html', quizzes=[results[q.id] for q in shown], results=results, fk=fk,
                           rules=RETAKE_RULES, title='Results by quiz', find_label='Find a quiz or student…')

#one quiz's results
@qgen_bp.route('/quiz/results/<int:vqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def quiz_results_page(vqid):
    from .models import RETAKE_RULES
    vq = db.session.get(VQuiz, vqid)
    if vq is None:
        return gone('That quiz has been deleted.', url_for('qgen.results_by_quiz'))
    return render_template('results_by_quiz.html', quizzes=quiz_results([vq]), rules=RETAKE_RULES, single=True,
                           title='Results: {}'.format(vq.title))

def quiz_results(quizzes):
    """[{'vquiz', 'rows': [(student, group from attempts_by_quiz)] by name, 'students', 'average'
    (of the scores that count, or None), 'waiting' (for grading), 'done' (students with a score)}]."""
    from .models import attempts_by_quiz
    out = []
    for vq in quizzes:
        mine = {}
        for cq in vq.cquizzes:
            if cq.taker:
                mine.setdefault(cq.assignee, []).append(cq)
        rows = sorted(((attempts[0].taker, attempts_by_quiz(attempts)[0]) for attempts in mine.values()),
                      key=lambda row: row[0].username.lower())
        scores = [g['combined'] for _, g in rows if g['combined'] is not None]
        out.append({'vquiz': vq, 'rows': rows, 'students': len(rows), 'done': len(scores),
                    'average': sum(scores) / len(scores) if scores else None,
                    'waiting': sum(1 for _, g in rows for cq in g['attempts'] if cq.status == 'review')})
    return out

#route to list contents/transcript of a specific concrete quiz
@qgen_bp.route('/quiz/listcq/<cqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_cquiz(cqid):
    cqlst = CQuiz.query.filter_by(id=cqid).first()
    if cqlst is None:
        return attempt_gone(cqid)
    shown = lambda cp: get_qtype(cp.vproblem.qtype).show_submitted(cp.submitted, cp.conc_opts)
    #a number answer as numbers (an old saved "sqrt(3)" shows as 1.7321), with its exact form
    correct = lambda cp: get_qtype('numeric').show_correct(cp.conc_ansr, cp.conc_opts) \
        if cp.vproblem.qtype == 'numeric' else cp.conc_ansr
    return render_template('cqlist.html', cqlst=[cqlst], shown=shown, correct=correct, title="{}'s attempt: {}".format(cqlst.taker.shown_name if cqlst.taker else 'Someone', cqlst.vquiz.title))

#route to delete a specific concrete quiz from a user's record
@qgen_bp.route('/quiz/delcq/<cqid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def del_cquiz(cqid):
    cq = CQuiz.query.filter_by(id=cqid).first_or_404('No CQuiz with id {}'.format(cqid))
    title, owner = cq.vquiz.title, cq.taker.shown_name
    archived = S.delete_attempt(cq, by=current_user)
    flash(Markup('Moved {}\'s attempt at "{}" to the archive. <a href="{}">View it</a>').format(
        owner, title, url_for('qgen.archived', aid=archived.id)), 'success')
    current_app.logger.info("{} archived {}'s CQuiz: ({}) '{}'".format(current_user.username, owner, cqid, title))
    return redirect(back_to(url_for('qgen.list_users')))

#route to reassign a specific concrete quiz to a user (a fresh copy with new values)
@qgen_bp.route('/quiz/retcq/<cqid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def ret_cquiz(cqid):
    cq0 = CQuiz.query.filter_by(id=cqid).first_or_404('No CQuiz with id {}'.format(cqid))
    try:
        cq = S.retake(cq0, by=current_user)
    except S.ServiceError as exc:
        flash(str(exc), 'error')
        current_app.logger.error(str(exc))
        return redirect(back_to(url_for('qgen.list_users')))
    flash('Assigned a retake of "{}" to {}.'.format(cq.vquiz.title, cq.taker.shown_name), 'success')
    current_app.logger.info('{} assigned retake (of {}) quiz: "{}" ({}) to {}'.format(current_user.username, cqid, cq.vquiz.title, cq.id, cq.taker.username))
    return redirect(back_to(url_for('qgen.list_users')))


# ---------------------------------------------------------------- AI helper

def ai_call(kind, text, work):
    """Every AI button goes through here: session check, API key, size and hourly
    limits, and the call log. `work(key, text)` returns (result, usage)."""
    from datetime import timedelta
    from .ai_helper import AIError
    from app import tuning
    hourly = tuning.get('ai_hourly')
    from .models import AICall
    if not json_csrf_ok():
        return None, (jsonify(ok=False, error='Your session expired. Please reload the page.'), 400)
    key = current_app.config.get('ANTHROPIC_API_KEY')
    if not key:
        return None, (jsonify(ok=False, error='The AI helper isn\'t set up (no API key).'), 400)
    text = (text or '').strip()
    if not text:
        return None, (jsonify(ok=False, error='Please describe what you want first.'), 400)
    if len(text) > 8000:
        return None, (jsonify(ok=False, error='That\'s too long for the AI helper; please shorten it.'), 400)
    since = datetime.now() - timedelta(hours=1)
    if AICall.query.filter(AICall.user_id == current_user.id, AICall.created >= since).count() >= hourly:
        return None, (jsonify(ok=False, error='You\'ve used the AI helper {} times in the last hour. Please wait a bit.'.format(hourly)), 429)
    call = AICall(user_id=current_user.id, created=datetime.now(), kind=kind, request=text, ok=False)
    try:
        result, usage = work(key, text)
        call.ok = True
        call.input_tokens, call.output_tokens = usage['input_tokens'], usage['output_tokens']
        return result, None
    except AIError as exc:
        return None, (jsonify(ok=False, error=str(exc)), 502)
    finally:
        db.session.add(call)
        db.session.commit()
        current_app.logger.info('{} used the AI helper ({}, ok={}, tokens in/out {}/{})'.format(
            current_user.username, kind, call.ok, call.input_tokens, call.output_tokens))

def ai_fill(kind):
    """Shared by both "Fill in for me" buttons; always answers with JSON."""
    from .ai_helper import ask, problems_with
    text = (request.get_json(silent=True) or {}).get('text')
    fill, failed = ai_call(kind, text, lambda key, t: ask(key, kind, t))
    if failed:
        return failed
    if fill.get('off_topic'):
        #the helper is for school quiz problems only; nothing else is filled in
        return jsonify(ok=False, error='The AI helper only writes school quiz problems. Please describe a quiz question for your students.'), 422
    return jsonify(ok=True, fill=fill, note=fill.get('cannot_do'), problems=problems_with(fill, kind))

@qgen_bp.route('/quiz/ai/problem', methods=['POST'])
@login_required
@pw_check
@admin_only
def ai_problem():
    return ai_fill('problem')

@qgen_bp.route('/quiz/ai/values', methods=['POST'])
@login_required
@pw_check
@admin_only
def ai_values():
    return ai_fill('values')


#a "Pick from list" value: fill its items from a description ("all the perfect squares from 4 to 100")
@qgen_bp.route('/quiz/ai/list', methods=['POST'])
@login_required
@pw_check
@admin_only
def ai_list():
    from .ai_helper import ask_list, describe_context
    data = request.get_json(silent=True) or {}
    name = str(data.get('name') or '')
    columns = len([p for p in name.split('=')]) if '=' in name else 1
    #the question and the other random values, so the description can refer to them
    context = describe_context(data.get('question'), data.get('values') if isinstance(data.get('values'), list) else [], name)
    result, failed = ai_call('list', data.get('text'), lambda key, t: ask_list(key, t, columns, context=context))
    if failed:
        return failed
    if result['off_topic']:
        return jsonify(ok=False, error='The AI helper only fills in lists for school quiz problems.'), 422
    if not result['items']:
        return jsonify(ok=False, error=result['cannot_do'] or 'The AI helper couldn\'t make that list. Please describe it another way.'), 422
    return jsonify(ok=True, items=', '.join(result['items']), count=len(result['items']), note=result['cannot_do'])


# ---------------------------------------------------------------- live helper

#problem page: rule-based hints as the teacher types (same form data as the preview)
@qgen_bp.route('/quiz/checkvprob', methods=['POST'])
@login_required
@pw_check
@admin_only
def check_vprob():
    from .coach import problem_hints
    form = ProblemForm()
    form.validate()
    return jsonify(hints=problem_hints(form.qtype.data, form.question.data, form.answer.data, form.options()))

#quiz page: hints about the checked problems
@qgen_bp.route('/quiz/checkvquiz', methods=['POST'])
@login_required
@pw_check
@admin_only
def check_vquiz():
    from .coach import quiz_hints
    form = QuizForm()
    try:
        lay = parse_vplist(form.vplist.data)
    except layout.LayoutError:
        lay = []
    vpids = layout.all_ids(lay)
    problems = {p.id: p for p in VProblem.query.filter(VProblem.id.in_(vpids)).all()} if vpids else {}
    vpids = [p for p in vpids if p in problems]
    this_id = request.args.get('vq', type=int)
    others = {q.title.strip().lower() for q in VQuiz.query.all() if q.id != this_id and q.title}
    return jsonify(hints=quiz_hints(form.title.data, vpids, form.calculator_ok.data, others, problems,
                                    lay=lay, shuffle_order=form.shuffle_order.data))


# ---------------------------------------------------------------- subjects

#the Problems and Quizzes pages' folders ("subjects" in the code), drawn like every other
#folder list on the site (app/templates/_folders.html); a problem or quiz can be in several

def subject_list(kind, **values):
    if kind not in LIST_PAGES:
        abort(404)
    return redirect(url_for(LIST_PAGES[kind], **values))

def subject_or_404(kind, sid):
    if kind not in LIST_PAGES:
        abort(404)
    return S.get_subject(kind, sid) or abort(404)

def _subject_done(kind, message, error=False, show=None, moved=None):
    """After a change to a page's folders: JSON for the page's script (a drag), else back to
    the page showing the same folder (or `show`), with what moved lit up."""
    if request.headers.get('X-Requested-With') == 'fetch':
        return (jsonify(ok=False, error=message), 400) if error else jsonify(ok=True, message=message)
    flash(message, 'error' if error else 'success')
    show = str(request.form.get('view') or 'all') if show is None else str(show)
    values = {'folder': show} if show.isdigit() or show == 'main' else {}
    if moved and not error:
        values['moved'] = moved
    return subject_list(kind, **values)

def _item_word(kind, n=1):
    return ('problem' if kind == 'problems' else 'quiz') if n == 1 else kind

def _item_title(kind, item_id):
    _g, item_cls, _r, _b = S.subject_kind(kind)
    item = db.session.get(item_cls, int(item_id)) if str(item_id).isdigit() else None
    return item.title if item else None

#route to make a new folder (at the top, or inside another: parent)
@qgen_bp.route('/quiz/subjects/<kind>/new', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def new_subject(kind):
    if kind not in LIST_PAGES:
        abort(404)
    parent = S.get_subject(kind, request.form.get('parent')) if request.form.get('parent') else None
    try:
        subject = S.create_subject(kind, request.form.get('name'), parent=parent)
    except S.ServiceError as exc:
        return _subject_done(kind, str(exc), error=True)
    current_app.logger.info('{} made {} folder ({}) "{}"'.format(current_user.username, kind, subject.id, subject.title))
    return _subject_done(kind, 'Folder "{}" made.'.format(subject.title))  # stay where you were

#route to rename a folder
@qgen_bp.route('/quiz/subjects/<kind>/<int:sid>/rename', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def rename_subject(kind, sid):
    subject = subject_or_404(kind, sid)
    try:
        S.rename_subject(kind, subject, request.form.get('name'))
    except S.ServiceError as exc:
        return _subject_done(kind, str(exc), error=True)
    return _subject_done(kind, 'Folder renamed to "{}".'.format(subject.title))

#route to remove a folder (nothing in it is deleted: it moves up a level)
@qgen_bp.route('/quiz/subjects/<kind>/<int:sid>/delete', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delete_subject(kind, sid):
    subject = subject_or_404(kind, sid)
    name, parent = subject.title, subject.parent_id
    S.delete_subject(subject, kind)
    current_app.logger.info('{} deleted {} folder ({}) "{}"'.format(current_user.username, kind, sid, name))
    return _subject_done(kind, 'Folder "{}" removed; the {} in it moved up a level.'.format(name, kind),
                         show=(parent or 'all') if request.form.get('view') == str(sid) else None)

#dragging (and the folder's "Move to" list): a problem or quiz onto a folder (from a folder:
#moved out of that one; from All or Not in a folder: put in it), onto Not in a folder (out
#of the folder it came from), or a folder onto a folder ("top": the top level)
@qgen_bp.route('/quiz/subjects/<kind>/move', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def move_subject(kind):
    if kind not in LIST_PAGES:
        abort(404)
    to, came_from = request.form.get('to'), request.form.get('from') or ''
    here = S.get_subject(kind, came_from) if came_from.isdigit() else None
    what = 'problem' if kind == 'problems' else 'quiz'
    try:
        if request.form.get('folder'):
            subject = subject_or_404(kind, request.form.get('folder'))
            target = S.get_subject(kind, to) if str(to).isdigit() else None
            S.move_subject(kind, subject, target)
            return _subject_done(kind, 'Moved "{}" to {}.'.format(subject.title, '"{}"'.format(target.title) if target else 'the top'),
                                 moved='folder:{}'.format(subject.id))
        item_id = request.form.get(what)
        if to in (None, '', 'top', 'main'):
            if here is None:
                return _subject_done(kind, 'Drag it out of a folder to take it out.', error=True)
            item = S.file_one(kind, item_id, here, add=False)
            return _subject_done(kind, 'Took "{}" out of "{}".'.format(item.title, here.title), moved='{}:{}'.format(what, item.id))
        target = subject_or_404(kind, to)
        item = S.file_one(kind, item_id, target, moving_from=here)
        return _subject_done(kind, ('Moved "{}" to "{}".' if here else 'Put "{}" in "{}".').format(item.title, target.title),
                             moved='{}:{}'.format(what, item.id))
    except S.ServiceError as exc:
        return _subject_done(kind, str(exc), error=True)

#one problem's (or quiz's) "+ Add to folder…" list (it stays in its others) and a folder chip's ✕
@qgen_bp.route('/quiz/subjects/<kind>/add', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def add_to_subject(kind):
    what = 'problem' if kind == 'problems' else 'quiz'
    target = subject_or_404(kind, request.form.get('to'))
    try:
        item = S.file_one(kind, request.form.get(what), target)
    except S.ServiceError as exc:
        return _subject_done(kind, str(exc), error=True)
    return _subject_done(kind, 'Put "{}" in "{}".'.format(item.title, target.title), moved='{}:{}'.format(what, item.id))

@qgen_bp.route('/quiz/subjects/<kind>/remove', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def remove_from_subject(kind):
    what = 'problem' if kind == 'problems' else 'quiz'
    folder = subject_or_404(kind, request.form.get('folder'))
    try:
        item = S.file_one(kind, request.form.get(what), folder, add=False)
    except S.ServiceError as exc:
        return _subject_done(kind, str(exc), error=True)
    return _subject_done(kind, 'Took "{}" out of "{}".'.format(item.title, folder.title))

#route to put the checked problems (or quizzes) in a folder, or take them out of it
@qgen_bp.route('/quiz/subjects/<kind>/file', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def file_subject(kind):
    if kind not in LIST_PAGES:
        abort(404)
    #"Add to" or "Remove from" the folder chosen in the menu
    add = request.form.get('action') != 'remove'
    subject = S.get_subject(kind, request.form.get('subject'))
    items = request.form.getlist('items')
    if subject is None:
        return _subject_done(kind, 'Choose a folder first.', error=True)
    if not items:
        return _subject_done(kind, 'Check at least one first.', error=True)
    count = S.file_items(kind, items, subject, add=add)
    return _subject_done(kind, '{} {} {} "{}".'.format(count, _item_word(kind, count), 'put in' if add else 'taken out of', subject.title))


def subject_kit(kind, view, node, root, flat, nodes):
    """The Problems or Quizzes page's folders, for _folders.html."""
    from app import folder_tree
    page = LIST_PAGES[kind]
    unit, units = ('problem', 'problems') if kind == 'problems' else ('quiz', 'quizzes')
    return folder_tree.kit(
        view, node, root, flat, nodes,
        page=lambda v: url_for(page, folder=v) if str(v) != 'all' else url_for(page),
        create_url=url_for('qgen.new_subject', kind=kind), move_url=url_for('qgen.move_subject', kind=kind),
        rename_url=lambda fid: url_for('qgen.rename_subject', kind=kind, sid=fid),
        delete_url=lambda fid: url_for('qgen.delete_subject', kind=kind, sid=fid),
        add_url=url_for('qgen.add_to_subject', kind=kind), remove_url=url_for('qgen.remove_from_subject', kind=kind),
        unit=unit, units=units, all_label='All ' + units, order=('all', 'main'), all_count=root['all_count'],
        name=lambda f: f.title, placeholder='e.g. Algebra', add_words='+ Add to folder…', drag_what='a ' + unit,
        hint='Your own folders for sorting {}, e.g. “Algebra” or “Period 2”. A {} can be in several folders. '
             'Students never see them.'.format(units, unit),
        fold_key='qgen-folded-{}-folders'.format(kind), open_key='qgen-open-{}-subfolders'.format(kind))


def subject_page(kind, template, **extra):
    """The Problems or Quizzes page: ?folder= all (the default), main (not in a folder) or a
    folder's id."""
    from app import folder_tree
    root, flat, nodes = S.subject_tree(kind)
    _g, item_cls, rel, _b = S.subject_kind(kind)
    everything = item_cls.query.order_by(item_cls.id.desc()).all()
    root['all_count'] = len(everything)
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='all')
    shown = node['items'] if node else everything if view == 'all' else root['items']
    fk = subject_kit(kind, view, node, root, flat, nodes)
    return render_template(template, fk=fk, items=shown, total=len(everything), kind=kind,
                           moved=request.args.get('moved', ''), show=request.args.get('show', ''), **extra)


# ---------------------------------------------------------------- the archive

def archived_for(cidx):
    """The archived copy of a live attempt's number, if there is one."""
    try:
        return ArchivedAttempt.query.filter_by(original_id=int(cidx)).order_by(ArchivedAttempt.id.desc()).first()
    except (TypeError, ValueError):
        return None

def gone(message, where):
    """A page whose subject was deleted (often reached by the page reloading itself when it
    happened): say so and go somewhere useful, not to "Not found"."""
    flash(message, 'info')
    return redirect(where)

def attempt_gone(cidx):
    """An attempt that isn't there: archived (tell the student plainly; teachers see the
    archived copy), or never existed."""
    a = archived_for(cidx)
    if a is None:
        abort(404)
    if current_user.is_admin:
        return redirect(url_for('qgen.archived', aid=a.id))
    if a.student_id != current_user.id:
        abort(404)
    flash('Your teacher has taken this quiz away.', 'info')
    return redirect(url_for('user.mypage'))

def archive_kit(view, node, root, flat, nodes, total):
    """The Archive's folders, for _folders.html."""
    from app import folder_tree
    return folder_tree.kit(
        view, node, root, flat, nodes,
        page=lambda v: url_for('qgen.archive', folder=v) if str(v) != 'all' else url_for('qgen.archive'),
        create_url=url_for('qgen.new_archive_folder'), move_url=url_for('qgen.move_archive_item'),
        rename_url=lambda fid: url_for('qgen.rename_archive_folder', fid=fid),
        delete_url=lambda fid: url_for('qgen.delete_archive_folder', fid=fid),
        unit='attempt', units='attempts', all_label='All archived', order=('all', 'main'), all_count=total,
        name=lambda f: f.name, folder_icon=lambda f: '👤' if f.student_id else '📁',
        placeholder='e.g. 2025-26', add_words='Move to…', drag_what='an attempt',
        hint='Each student has a folder (👤) for their archived attempts; you can add your own and put folders inside folders.',
        fold_key='qgen-folded-archive-folders', open_key='qgen-open-archive-subfolders')

def _archive_done(message, error=False, show=None, moved=None):
    """After a change to the Archive's folders: JSON for the page's script (a drag), else back
    to the Archive showing the same folder (or `show`)."""
    if request.headers.get('X-Requested-With') == 'fetch':
        return (jsonify(ok=False, error=message), 400) if error else jsonify(ok=True, message=message)
    flash(message, 'error' if error else 'success')
    show = str(request.form.get('view') or 'all') if show is None else str(show)
    values = {'folder': show} if show.isdigit() or show == 'main' else {}
    if moved and not error:
        values['moved'] = moved
    return redirect(url_for('qgen.archive', **values))

#route to the archive of deleted attempts: ?folder= all (the default), main (not in a folder)
#or a folder's id
@qgen_bp.route('/quiz/archive', methods=['GET'])
@login_required
@pw_check
@admin_only
def archive():
    from app import folder_tree
    root, flat, nodes, attempts = S.archive_tree()
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='all')
    shown = node['items'] if node else attempts if view == 'all' else root['items']
    #whether each attempt shown (here or in the folder boxes) can be put back
    showing = list(shown)
    if node:
        todo = list(node['folders'])
        while todo:
            n = todo.pop()
            showing += n['items']
            todo += n['folders']
    blockers = {a.id: S.restore_blocker(a) for a in showing}
    fk = archive_kit(view, node, root, flat, nodes, len(attempts))
    return render_template('archive.html', fk=fk, items=shown, blockers=blockers, total=len(attempts), title='Archive',
                           moved=request.args.get('moved', ''))

def archive_folder_or_404(fid):
    folder = S.get_archive_folder(fid)
    if folder is None:
        abort(404)
    return folder

#route to make an Archive folder of the teacher's own (at the top, or inside another)
@qgen_bp.route('/quiz/archive/folders/new', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def new_archive_folder():
    parent = S.get_archive_folder(request.form.get('parent')) if request.form.get('parent') else None
    try:
        folder = S.create_archive_folder(request.form.get('name'), parent=parent)
    except S.ServiceError as exc:
        return _archive_done(str(exc), error=True)
    return _archive_done('Folder "{}" made.'.format(folder.name))  # stay where you were

#route to rename an Archive folder
@qgen_bp.route('/quiz/archive/folders/<int:fid>/rename', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def rename_archive_folder(fid):
    folder = archive_folder_or_404(fid)
    try:
        S.rename_archive_folder(folder, request.form.get('name'))
    except S.ServiceError as exc:
        return _archive_done(str(exc), error=True)
    return _archive_done('Folder renamed to "{}".'.format(folder.name))

#route to remove an Archive folder (what's in it moves up a level)
@qgen_bp.route('/quiz/archive/folders/<int:fid>/delete', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delete_archive_folder(fid):
    folder = archive_folder_or_404(fid)
    name, parent = folder.name, folder.parent_id
    S.delete_archive_folder(folder)
    current_app.logger.info('{} deleted archive folder ({}) "{}"'.format(current_user.username, fid, name))
    return _archive_done('Folder "{}" removed; what was in it moved up a level.'.format(name),
                         show=(parent or 'all') if request.form.get('view') == str(fid) else None)

#dragging, and the "Move to…" lists: an archived attempt onto a folder (or Not in a folder),
#or a folder onto a folder ("top": the top level)
@qgen_bp.route('/quiz/archive/folders/move', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def move_archive_item():
    to = request.form.get('to')
    target = None if to in (None, '', 'top', 'main') else S.get_archive_folder(to)
    if to not in (None, '', 'top', 'main') and target is None:
        return _archive_done('That folder doesn\'t exist any more.', error=True)
    where = '"{}"'.format(target.name) if target else S.UNSORTED
    try:
        if request.form.get('folder'):
            folder = archive_folder_or_404(request.form.get('folder'))
            S.move_archive_folder(folder, target)
            return _archive_done('Moved "{}" to {}.'.format(folder.name, '"{}"'.format(target.name) if target else 'the top'),
                                 moved='folder:{}'.format(folder.id))
        a = db.session.get(ArchivedAttempt, int(request.form.get('attempt'))) if str(request.form.get('attempt', '')).isdigit() else None
        if a is None:
            return _archive_done('That archived attempt isn\'t there any more.', error=True)
        S.move_archived([a.id], target)
        return _archive_done('Moved {}\'s "{}" to {}.'.format(a.student_name, a.quiz_title, where), moved='attempt:{}'.format(a.id))
    except S.ServiceError as exc:
        return _archive_done(str(exc), error=True)

#route to move the checked archived attempts to a folder (or to Not in a folder)
@qgen_bp.route('/quiz/archive/move', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def move_archived():
    target = request.form.get('folder', '')
    folder = None if target in ('unsorted', 'top') else S.get_archive_folder(target)
    if target not in ('unsorted', 'top') and folder is None:
        return _archive_done('Choose a folder first.', error=True)
    moved = S.move_archived(request.form.getlist('items'), folder)
    if not moved:
        return _archive_done('Check at least one first.', error=True)
    return _archive_done('Moved {} attempt{} to {}.'.format(moved, '' if moved == 1 else 's',
                                                             '"{}"'.format(folder.name) if folder else S.UNSORTED))

#route to look at one archived attempt
@qgen_bp.route('/quiz/archive/<int:aid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def archived(aid):
    a = db.session.get(ArchivedAttempt, aid)
    if a is None:
        return gone("That attempt isn't in the Archive any more: it was put back or deleted for good.", url_for('qgen.archive'))
    return render_template('archived.html', a=a, blocker=S.restore_blocker(a),
                           student=S.archived_student(a), results=S.archived_results(a),
                           title='Archived: {}'.format(a.quiz_title))

#route to put an archived attempt back
@qgen_bp.route('/quiz/archive/<int:aid>/restore', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def restore_archived(aid):
    a = db.get_or_404(ArchivedAttempt, aid)
    name, title = a.student_name, a.quiz_title
    try:
        cq = S.restore_attempt(a)
    except S.ServiceError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('qgen.archived', aid=aid))
    flash('Restored {}\'s attempt at "{}"; {} can see it again.'.format(name, title, name), 'success')
    current_app.logger.info('{} restored {}\'s CQuiz ({}) "{}"'.format(current_user.username, name, cq.id, title))
    return redirect(url_for('qgen.list_user', uid=cq.assignee))

#route to delete an archived attempt for good
@qgen_bp.route('/quiz/archive/<int:aid>/delete', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def purge_archived(aid):
    a = db.get_or_404(ArchivedAttempt, aid)
    name, title, original = a.student_name, a.quiz_title, a.original_id
    S.purge_archived(a)
    flash('Deleted {}\'s attempt at "{}" for good.'.format(name, title), 'success')
    current_app.logger.info('{} purged archived CQuiz ({}) of {} "{}"'.format(current_user.username, original, name, title))
    return redirect(url_for('qgen.archive'))


# ---------------------------------------------------------------- the Dashboard

def dashboard_data():
    """Everything the Dashboard shows, fresh."""
    from . import dashboard as D
    now = datetime.now()
    queue, waiting = D.grading_queue()
    out, out_total = D.out_now(now)
    return {'counts': D.counts(current_user, now), 'online': D.online(now), 'recent': D.recently_active(now),
            'taking': D.taking_now(now), 'now': now, 'when': lambda d: D.when(d, now),
            'queue': queue, 'waiting': waiting, 'handins': D.recent_handins(), 'out': out, 'out_total': out_total, 'glance': D.site_glance(now),
            'pinned': D.pinned()}

#route to the administrators' landing page: what needs doing and what's going on
@qgen_bp.route('/dashboard', methods=['GET'])
@login_required
@pw_check
@admin_only
def dashboard():
    from app import tuning
    return render_template('dashboard.html', title='Dashboard', refresh_ms=tuning.dashboard_ms(), **dashboard_data())

#route to the top bar's "online" list (opened from any teacher page)
@qgen_bp.route('/dashboard/online', methods=['GET'])
@login_required
@pw_check
@admin_only
def dashboard_online():
    from . import dashboard as D
    now = datetime.now()
    return render_template('_online_list.html', online=D.online(now), recent=D.recently_active(now), now=now)

#route to the Dashboard's contents again, for its refresh every 30 seconds
@qgen_bp.route('/dashboard/now', methods=['GET'])
@login_required
@pw_check
@admin_only
def dashboard_now():
    return render_template('_dashboard_live.html', **dashboard_data())
