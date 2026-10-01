from . import db, qgen_bp
from app.user.models import User
from app.user.routes import admin_only, pw_check
from .formfact import quiz_form_class, quiz_items, form_answers, transcript_html, transcript_item, fieldname_base
from . import services as S
from .forms import ProblemForm, QuizForm, AssignForm, ReviewForm
from .models import CQuiz, VQuiz, VProblem
from .qtypes import get_qtype, REGISTRY
from .friendly import KINDS, FriendlyError
from . import layout
from flask import flash, render_template, redirect, url_for, request, current_app, abort, jsonify
from app.jsoncsrf import json_csrf_ok, post_form_only
from flask_login import current_user, login_required
from datetime import datetime, timedelta
import json
import random

def parse_vplist(text):
    """The quiz's problem list from the form: single ids and groups."""
    return layout.parse(text)


# ---------------------------------------------------------------- problems

def problem_page(form, vp, errors, title):
    #unbound copy with one empty row of each kind, cloned by problem_form.js for "+ Add"
    blank = ProblemForm(formdata=None)
    blank.values.append_entry()
    blank.images.append_entry()
    return render_template('problem_form.html', form=form, vp=vp, errors=errors, title=title, blank=blank,
                           kinds=KINDS, qtypes=REGISTRY, ai_enabled=bool(current_app.config.get('ANTHROPIC_API_KEY')))

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
    errors = []
    if form.validate_on_submit():
        nuprob = VProblem(author_id=current_user.id)
        errors = save_from_form(form, nuprob)
        if not errors:
            flash('Saved problem "{}".'.format(nuprob.title), 'success')
            current_app.logger.info('{} created VProblem: ({}) "{}"'.format(current_user.username, nuprob.id, nuprob.title))
            return redirect(url_for('qgen.list_vprobs'))
    elif request.method == 'GET' and not form.values.entries:
        form.values.append_entry()
    return problem_page(form, None, errors, 'New problem')

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
    errors = []
    if request.method == 'GET':
        form.load(vpobj)
    elif form.validate_on_submit():
        errors = save_from_form(form, vpobj)
        if not errors:
            flash('Updated problem "{}". Quizzes already assigned keep the version they were given.'.format(vpobj.title), 'success')
            current_app.logger.info('{} updated VProblem: ({}) "{}"'.format(current_user.username, vpobj.id, vpobj.title))
            return redirect(url_for('qgen.list_vprobs'))
    return problem_page(form, vpobj, errors, 'Edit problem')

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
    vplst = VProblem.query.order_by(VProblem.id.desc()).all()
    return render_template('vplist.html', vplst=vplst, qtypes=REGISTRY, title='Problems')

#route to list a specific virtual problem
@qgen_bp.route('/quiz/listvp/<vpid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vprob(vpid):
    vplst = VProblem.query.filter_by(id=vpid).first_or_404('No vproblem with id {}'.format(vpid))
    return render_template('vplist.html', vplst=[vplst], qtypes=REGISTRY, title='Problem {}'.format(vpid))

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

def quiz_page(form, title, vq=None):
    probs = VProblem.query.order_by(VProblem.id.desc()).all()
    return render_template('quiz_form.html', form=form, title=title, probs=probs, qtypes=REGISTRY, vq=vq,
                           ai_enabled=bool(current_app.config.get('ANTHROPIC_API_KEY')))

def save_quiz_from_form(form, vq):
    errors = S.save_vquiz(vq, form.title.data, form.vplist.data, author_id=current_user.id,
                          image=form.image.data or None, calculator_ok=form.calculator_ok.data,
                          shuffle_order=form.shuffle_order.data, retake_rule=form.retake_rule.data,
                          hide_answers=form.hide_answers.data)
    form.vplist.errors = errors
    return errors

#route to create a virtual quiz
@qgen_bp.route('/quiz/makevquiz', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def mkvquiz():
    form = QuizForm()
    if form.validate_on_submit():
        nq = VQuiz()
        if not save_quiz_from_form(form, nq):
            count = layout.question_count(layout.parse(nq.vpid_lst))
            flash('Created quiz "{}": each student gets {} question{}.'.format(nq.title, count, '' if count == 1 else 's'), 'success')
            current_app.logger.info('{} created VQuiz: ({}) "{}"'.format(current_user.username, nq.id, nq.title))
            return redirect(url_for('qgen.list_vquizzes'))
    return quiz_page(form, 'New quiz')

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
    vqobj = VQuiz.query.filter_by(id=vqid).first_or_404('No VQuiz with id {}'.format(vqid))
    form = QuizForm(obj=vqobj)
    if request.method == 'GET':
        form.vplist.data = layout.dumps(layout.parse(vqobj.vpid_lst))
    elif form.validate_on_submit():
        if not save_quiz_from_form(form, vqobj):
            flash('Updated quiz "{}". Quizzes already assigned keep the version they were given.'.format(vqobj.title), 'success')
            current_app.logger.info('{} updated VQuiz: ({}) "{}"'.format(current_user.username, vqobj.id, vqobj.title))
            return redirect(url_for('qgen.list_vquizzes'))
    return quiz_page(form, 'Edit quiz', vqobj)

#route to list all virtual quizzes
@qgen_bp.route('/quiz/listvq', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vquizzes():
    vqlst = VQuiz.query.order_by(VQuiz.id.desc()).all()
    return render_template('vqlist.html', vqlst=vqlst, title='Quizzes', layout=layout)

#route to list a specific virtual quiz
@qgen_bp.route('/quiz/listvq/<vqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vquiz(vqid):
    vqlst = VQuiz.query.filter_by(id=vqid).first_or_404('No VQuiz with id {}'.format(vqid))
    return render_template('vqlist.html', vqlst=[vqlst], title='Quiz {}'.format(vqid), layout=layout)

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


#route to show (or hide again) correct answers on students' results pages
@qgen_bp.route('/quiz/releasevq/<vqid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def release_vquiz(vqid):
    vq = db.get_or_404(VQuiz, vqid)
    S.release_answers(vq, not vq.answers_released)
    flash('Correct answers for "{}" are now {} to students.'.format(vq.title, 'shown' if vq.answers_released else 'hidden'), 'success')
    return redirect(request.referrer or url_for('qgen.list_vquizzes'))


#route to show (or hide again) the correct answers to one student: all of that
#student's attempts at the quiz of the attempt given
@qgen_bp.route('/quiz/releasecq/<cqid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def release_to_student(cqid):
    cq = db.get_or_404(CQuiz, cqid)
    released = not cq.answers_released
    S.release_answers_to(cq.vquiz, cq.assignee, released)
    flash('Correct answers for "{}" are now {} to {}.'.format(cq.vquiz.title, 'shown' if released else 'hidden', cq.taker.username), 'success')
    return redirect(request.referrer or url_for('qgen.list_user', uid=cq.assignee))


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
    flash('{}\'s score for "{}" is now: {}.'.format(cq.taker.username, cq.vquiz.title,
          RETAKE_RULES[rule].lower() if rule else 'the quiz\'s own rule'), 'success')
    return redirect(request.referrer or url_for('qgen.list_user', uid=cq.assignee))


# ---------------------------------------------------------------- assigning

#route to assign a concrete quiz to one or more users
@qgen_bp.route('/quiz/assign', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def assign():
    form = AssignForm()
    form.vquiz.choices = [(q.id, q.title) for q in VQuiz.query.order_by(VQuiz.title).all()]
    form.users.choices = [(u.id, u.username) for u in User.query.order_by(User.username).all()]
    if request.method == 'GET' and request.args.get('vq', '').isdigit():
        form.vquiz.data = int(request.args['vq'])
    if form.validate_on_submit():
        vquiz = db.get_or_404(VQuiz, form.vquiz.data)
        students = [db.session.get(User, uid) for uid in form.users.data]
        created, failed = S.assign(vquiz, [u for u in students if u], form.opens_at.data, form.closes_at.data, form.time_limit.data,
                                   by=current_user)
        for student, err in failed:
            flash(err, 'error')
            current_app.logger.error(err)
        for cq in created:
            current_app.logger.info('{} assigned quiz: "{}" ({}) to {}'.format(current_user.username, vquiz.title, cq.id, cq.taker.username))
        if created:
            flash('Assigned "{}" to {}.'.format(vquiz.title, ', '.join(cq.taker.username for cq in created)), 'success')
        return redirect(url_for('qgen.assign'))
    return render_template('assign.html', title='Assign a quiz', form=form)


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
    cq = CQuiz.query.filter_by(id=cidx).first_or_404('No CQuiz with id {}'.format(cidx))
    if not cq.taker:
        flash('That quiz is not assigned to anyone.', 'error')
        return redirect(url_for('user.mypage'))
    if current_user != cq.taker and not current_user.is_admin:
        flash('That quiz belongs to someone else.', 'error')
        return redirect(url_for('user.mypage'))
    title = cq.vquiz.title
    is_taker = current_user == cq.taker
    state = S.attempt_state(cq)
    if state == 'completed':
        show = cq.answers_visible or current_user.is_admin
        return render_template('transcript.html', cq=cq, title=title,
                               transcript=transcript_html(cq, title, show_answers=show), answers_hidden=not show)
    if state == 'review':
        return render_template('awaiting.html', cq=cq, title=title)
    if state == 'not_open' and is_taker:
        return render_template('not_open.html', cq=cq, title=title)
    #out of time: close it with whatever was autosaved
    if state == 'time_up' and is_taker:
        S.submit(cq)
        flash('Time ran out, so your saved answers were submitted.', 'info')
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
        flash("Only {} can submit this quiz.".format(cq.taker.username), 'error')
    if request.method == 'GET':
        prefill(cq, form)
    return render_template('quiz_take.html', cq=cq, form=form, items=quiz_items(cq, form), title=title,
                           preview=not is_taker, deadline=cq.deadline())

#autosave: the quiz page sends the answers so far every few seconds
@qgen_bp.route('/quiz/take/<cidx>/save', methods=['POST'])
@login_required
@pw_check
def qsave(cidx):
    cq = CQuiz.query.filter_by(id=cidx).first_or_404()
    if current_user != cq.taker:
        return jsonify(ok=False, error='Not your quiz.'), 403
    if not json_csrf_ok():
        return jsonify(ok=False, error='Your session expired. Please reload the page.'), 400
    form = quiz_form_class(cq)(meta={'csrf': False})
    #only questions the page sent (a question with nothing ticked sends just its marker)
    sent = {cp.ordinal: form[fieldname_base.format(cp.ordinal)].data for cp in cq.cproblems
            if fieldname_base.format(cp.ordinal) in request.form or fieldname_base.format(cp.ordinal) + '_present' in request.form}
    try:
        S.autosave(cq, sent)
    except S.ServiceError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    return jsonify(ok=True, saved=datetime.now().strftime('%I:%M:%S %p').lstrip('0'))


# ---------------------------------------------------------------- review

#route to list quizzes waiting for an instructor
@qgen_bp.route('/quiz/review', methods=['GET'])
@login_required
@pw_check
@admin_only
def review_list():
    waiting = CQuiz.query.filter_by(needs_review=True, completed=False).order_by(CQuiz.compdate).all()
    return render_template('review_list.html', waiting=waiting, title='Waiting for grading')

#route to grade the essay answers of one quiz
@qgen_bp.route('/quiz/review/<cqid>', methods=['GET', 'POST'])
@login_required
@pw_check
@admin_only
def review(cqid):
    cq = db.get_or_404(CQuiz, cqid)
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
            ungraded = S.grade_essays(cq, grades, finish=bool(form.finalize.data), grader_id=current_user.id)
        except S.ServiceError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('qgen.review', cqid=cq.id))
        if ungraded:
            flash('Give a credit for question{} {} before finishing.'.format('s' if len(ungraded) > 1 else '', ', '.join(map(str, ungraded))), 'error')
            return redirect(url_for('qgen.review', cqid=cq.id))
        if form.finalize.data:
            flash('Finished grading {}\'s "{}": {:.0f}%.'.format(cq.taker.username, cq.vquiz.title, cq.score), 'success')
            current_app.logger.info('{} graded CQuiz ({}) for {}'.format(current_user.username, cq.id, cq.taker.username))
            return redirect(url_for('qgen.review_list'))
        flash('Draft saved.', 'success')
        return redirect(url_for('qgen.review', cqid=cq.id))
    entries = {int(e.form.cpid.data): e.form for e in form.items}
    items = [dict(item=transcript_item(cp), cp=cp, form=entries.get(cp.id),
                  notes=cp.vproblem.options.get('grading_notes'), raw=cp.submitted or '')
             for cp in cq.cproblems]
    return render_template('review.html', cq=cq, form=form, items=items, title='Grade: {} – {}'.format(cq.taker.username, cq.vquiz.title))


# ---------------------------------------------------------------- students

#route to list users
@qgen_bp.route('/quiz/listuser', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_users():
    ulst = User.query.order_by(User.username).all()
    from .models import RETAKE_RULES
    return render_template('ulist.html', ulst=ulst, rules=RETAKE_RULES, title='Results by student')

#route to list a specific user
@qgen_bp.route('/quiz/listuser/<uid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_user(uid):
    ulst = User.query.filter_by(id=uid).first_or_404('No user with id {}'.format(uid))
    from .models import RETAKE_RULES
    return render_template('ulist.html', ulst=[ulst], rules=RETAKE_RULES, title="{}'s quizzes".format(ulst.username))

#route to list contents/transcript of a specific concrete quiz
@qgen_bp.route('/quiz/listcq/<cqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_cquiz(cqid):
    cqlst = CQuiz.query.filter_by(id=cqid).first_or_404('No cquiz with id {}'.format(cqid))
    shown = lambda cp: get_qtype(cp.vproblem.qtype).show_submitted(cp.submitted, cp.conc_opts)
    return render_template('cqlist.html', cqlst=[cqlst], shown=shown, title='Assigned quiz {}'.format(cqid))

#route to delete a specific concrete quiz from a user's record
@qgen_bp.route('/quiz/delcq/<cqid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def del_cquiz(cqid):
    cq = CQuiz.query.filter_by(id=cqid).first_or_404('No CQuiz with id {}'.format(cqid))
    title, owner = cq.vquiz.title, cq.taker.username
    S.delete_attempt(cq)
    flash('Deleted {}\'s "{}".'.format(owner, title), 'success')
    current_app.logger.info("{} deleted {}'s CQuiz: ({}) '{}'".format(current_user.username, owner, cqid, title))
    return redirect(request.referrer or url_for('qgen.list_users'))

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
        return redirect(request.referrer or url_for('qgen.list_users'))
    flash('Assigned a retake of "{}" to {}.'.format(cq.vquiz.title, cq.taker.username), 'success')
    current_app.logger.info('{} assigned retake (of {}) quiz: "{}" ({}) to {}'.format(current_user.username, cqid, cq.vquiz.title, cq.id, cq.taker.username))
    return redirect(request.referrer or url_for('qgen.list_users'))


# ---------------------------------------------------------------- AI helper

def ai_call(kind, text, work):
    """Every AI button goes through here: session check, API key, size and hourly
    limits, and the call log. `work(key, text)` returns (result, usage)."""
    from datetime import timedelta
    from .ai_helper import AIError, HOURLY_LIMIT
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
    if AICall.query.filter(AICall.user_id == current_user.id, AICall.created >= since).count() >= HOURLY_LIMIT:
        return None, (jsonify(ok=False, error='You\'ve used the AI helper {} times in the last hour. Please wait a bit.'.format(HOURLY_LIMIT)), 429)
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

def describe_problem(form):
    """A problem as plain text for the AI reviewer, with two sample versions."""
    opts = form.options()
    qt = get_qtype(form.qtype.data)
    lines = ['Question type: ' + qt.label, 'Question: ' + (form.question.data or '')]
    for v in opts['values']:
        lines.append('Value {}: {}'.format(v.get('name'), ', '.join('{}={}'.format(k, v[k]) for k in v if k != 'name')))
    if qt.uses_choices:
        lines.append('Choices (* = correct):\n' + opts['choices'])
        if opts.get('combos'):
            lines.append('Other correct combinations:\n' + opts['combos'])
        lines.append('Shuffled per student: {}; show only: {}'.format(opts['shuffle'], opts['show_n'] or 'all'))
    else:
        lines.append('{}: {}'.format(qt.answer_label, form.answer.data or ''))
    if qt.key == 'numeric':
        lines.append('Answer must be: ' + opts['precision'])
        lines.append('Order of several numbers matters: {}'.format(opts['ordered']))
    if opts['images']:
        lines.append('Pictures: ' + ', '.join('{} ({})'.format(i['file'], i['label'] or 'no label') for i in opts['images']))
    if not qt.validate(form.question.data, form.answer.data, opts):
        rng = random.Random(1)
        for n in (1, 2):
            prob, ansr, co = qt.instantiate(form.question.data, form.answer.data, opts, rng)
            lines.append('Sample student version {}: {} | correct: {}{}'.format(
                n, prob, qt.show_correct(ansr, co), ' | choices: ' + ' / '.join(co['choices']) if co.get('choices') else ''))
    return '\n'.join(lines)

def describe_quiz(form):
    try:
        lay = parse_vplist(form.vplist.data)
    except layout.LayoutError:
        lay = []
    lines = ['Quiz title: ' + (form.title.data or ''), 'Calculator allowed: {}'.format(form.calculator_ok.data),
             'Question order shuffled per student: {}'.format(form.shuffle_order.data)]
    def one(pid, prefix=''):
        p = db.session.get(VProblem, pid)
        if p:
            lines.append('{}- [{}] {}: {}'.format(prefix, get_qtype(p.qtype).label, p.title, p.raw_prob))
    for e in lay:
        if layout.is_group(e):
            lines.append('Group: each student gets {} of these {}:'.format(e['pick'], len(e['from'])))
            for pid in e['from']:
                one(pid, '  ')
        else:
            one(e)
    return '\n'.join(lines)

@qgen_bp.route('/quiz/ai/reviewproblem', methods=['POST'])
@login_required
@pw_check
@admin_only
def ai_review_problem():
    from .ai_helper import review
    form = ProblemForm()
    form.validate()
    tips, failed = ai_call('review', describe_problem(form), review)
    return failed or jsonify(ok=True, hints=tips)

@qgen_bp.route('/quiz/ai/reviewquiz', methods=['POST'])
@login_required
@pw_check
@admin_only
def ai_review_quiz():
    from .ai_helper import review
    form = QuizForm()
    tips, failed = ai_call('review', describe_quiz(form), review)
    return failed or jsonify(ok=True, hints=tips)

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

#quiz page: hints about the ticked problems
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
