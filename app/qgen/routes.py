from . import db, qgen_bp
from app.user.models import User
from app.user.routes import admin_only, pw_check
from .formfact import quiz_form_class, quiz_items, record_answers, finalize, transcript_html, transcript_item
from .forms import ProblemForm, QuizForm, AssignForm, ReviewForm
from .models import CQuiz, VQuiz, VProblem, CProblem, VPGroup, VQGroup
from .qtypes import get_qtype, REGISTRY
from .friendly import KINDS, FriendlyError
from flask import flash, render_template, redirect, url_for, request, current_app, abort, jsonify
from app.jsoncsrf import json_csrf_ok
from flask_login import current_user, login_required
from re import findall
from json import dumps, loads
from datetime import datetime
import json
import random

#generate a concrete problem: this student's own random version
def gen_cprob(cquiz, vprob, ordinal):
    qt = get_qtype(vprob.qtype)
    cp, ca, opts = qt.instantiate(vprob.raw_prob, vprob.raw_ansr, vprob.options)
    nucprob = CProblem(ordinal=ordinal, cquiz_id=cquiz.id, conc_prob=cp, conc_ansr=ca, vproblem_id=vprob.id)
    nucprob.conc_opts = opts
    return nucprob

def archive(obj, group_cls, rel):
    group = group_cls.query.filter_by(title='Archive').first()
    if group:
        getattr(obj, rel).append(group)

#generate a virtual quiz
def create_vquiz(lst, title, img, calculator_ok, shuffle_order=True):
    nuquiz = VQuiz(image=img, title=title, vpid_lst=dumps(lst), author_id=current_user.id, calculator_ok=calculator_ok, shuffle_order=shuffle_order)
    nuquiz.save()
    probs = [VProblem.query.filter_by(id=a).first_or_404('No vproblem with id {}'.format(a)) for a in set(lst)]
    nuquiz.vproblems.extend(probs)
    archive(nuquiz, VQGroup, 'vqgroups')
    nuquiz.save()
    return nuquiz

#generate a concrete quiz using virtual and assign to a user
def create_cquiz(vquiz, assignee):
    try:
        nuquiz = CQuiz(vquiz_id=vquiz.id, assignee=assignee.id)
        ordered_vids = loads(vquiz.vpid_lst)
        #so "question 1 is B" means nothing to the student next door
        if vquiz.shuffle_order:
            random.shuffle(ordered_vids)
        vprobs = [(o, VProblem.query.filter_by(id=vid).first()) for o, vid in enumerate(ordered_vids, 1)]
        probs = [gen_cprob(nuquiz, vp, o) for o,vp in vprobs]
        nuquiz.cproblems.extend(probs)
        nuquiz.save()
        return nuquiz
    except Exception as exc:
        current_app.logger.error(str(exc))
        flash(str(exc), 'error')
        db.session.rollback()
        return None

def parse_vplist(text):
    return [int(a) for a in findall(r'(\d+)', text or '')]


# ---------------------------------------------------------------- problems

#shared by create and edit: returns (errors, options) after checking the form
def check_problem(form):
    opts = form.options()
    qt = get_qtype(form.qtype.data)
    return qt.validate(form.question.data, form.answer.data, opts), opts

def problem_page(form, vp, errors, title):
    #unbound copy with one empty row of each kind, cloned by problem_form.js for "+ Add"
    blank = ProblemForm(formdata=None)
    blank.values.append_entry()
    blank.images.append_entry()
    return render_template('problem_form.html', form=form, vp=vp, errors=errors, title=title, blank=blank,
                           kinds=KINDS, qtypes=REGISTRY, ai_enabled=bool(current_app.config.get('ANTHROPIC_API_KEY')))

def save_problem(form, vp, opts):
    vp.qtype = form.qtype.data
    vp.title = form.title.data
    vp.raw_prob = form.question.data
    vp.raw_ansr = form.answer.data
    vp.options = opts
    #first picture kept in the old column for older pages and quizzes
    vp.image = opts['images'][0]['file'] if opts['images'] else None
    vp.calculator_ok = form.calculator_ok.data
    vp.save()

#route to create a virtual problem
@qgen_bp.route('/quiz/makevprob', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def mkvprob():
    form = ProblemForm()
    errors = []
    if form.validate_on_submit():
        errors, opts = check_problem(form)
        if not errors:
            nuprob = VProblem(author_id=current_user.id)
            archive(nuprob, VPGroup, 'vpgroups')
            save_problem(form, nuprob, opts)
            flash('Saved problem "{}".'.format(nuprob.title), 'success')
            current_app.logger.info('{} created VProblem: ({}) "{}"'.format(current_user.username, nuprob.id, nuprob.title))
            return redirect(url_for('qgen.list_vprobs'))
    elif request.method == 'GET' and not form.values.entries:
        form.values.append_entry()
    return problem_page(form, None, errors, 'New problem')

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
        errors, opts = check_problem(form)
        if not errors:
            save_problem(form, vpobj, opts)
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
    errors, opts = check_problem(form)
    samples = []
    if not errors:
        qt = get_qtype(form.qtype.data)
        rng = random.Random()
        for _ in range(3):
            prob, ansr, co = qt.instantiate(form.question.data, form.answer.data, opts, rng)
            samples.append(dict(text=prob, correct=qt.show_correct(ansr, co), choices=co.get('choices'),
                                right=co.get('correct', []), image=co.get('image')))
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
@qgen_bp.route('/quiz/delvp/<vpid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def del_vprob(vpid):
    vpquery = VProblem.query.filter_by(id=vpid)
    vp = vpquery.first_or_404('No VProblem with id {}'.format(vpid))
    title = vp.title
    vq = vp.vquizzes
    if vq:
        estr = 'Problem "{}" was not deleted because these quizzes use it: {}.'.format(title, ', '.join('"{}"'.format(q.title) for q in vq))
        current_app.logger.error(estr)
        flash(estr, 'error')
    else:
        vpquery.delete()
        db.session.commit()
        flash('Deleted problem "{}".'.format(title), 'success')
        current_app.logger.info("{} deleted VProblem: ({}) '{}'".format(current_user.username, vpid, title))
    return redirect(url_for('qgen.list_vprobs'))


# ---------------------------------------------------------------- quizzes

def quiz_page(form, title, vq=None):
    probs = VProblem.query.order_by(VProblem.id.desc()).all()
    return render_template('quiz_form.html', form=form, title=title, probs=probs, qtypes=REGISTRY, vq=vq)

def checked_vplist(form):
    numlist = parse_vplist(form.vplist.data)
    if not numlist:
        form.vplist.errors = ['Tick at least one problem.']
        return None
    missing = [n for n in set(numlist) if not db.session.get(VProblem, n)]
    if missing:
        form.vplist.errors = ['These problems no longer exist: {}'.format(', '.join(map(str, missing)))]
        return None
    return numlist

#route to create a virtual quiz
@qgen_bp.route('/quiz/makevquiz', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def mkvquiz():
    form = QuizForm()
    if form.validate_on_submit():
        numlist = checked_vplist(form)
        if numlist:
            nq = create_vquiz(numlist, form.title.data, form.image.data or None, form.calculator_ok.data, form.shuffle_order.data)
            flash('Created quiz "{}" with {} problem{}.'.format(nq.title, len(numlist), '' if len(numlist) == 1 else 's'), 'success')
            current_app.logger.info('{} created VQuiz: ({}) "{}"'.format(current_user.username, nq.id, nq.title))
            return redirect(url_for('qgen.list_vquizzes'))
    return quiz_page(form, 'New quiz')

#route to edit a specific virtual quiz
@qgen_bp.route('/quiz/editvquiz/<vqid>', methods=['POST', 'GET'])
@login_required
@pw_check
@admin_only
def edvquiz(vqid):
    vqobj = VQuiz.query.filter_by(id=vqid).first_or_404('No VQuiz with id {}'.format(vqid))
    form = QuizForm(obj=vqobj)
    if request.method == 'GET':
        form.vplist.data = ', '.join(map(str, loads(vqobj.vpid_lst or '[]')))
    elif form.validate_on_submit():
        numlist = checked_vplist(form)
        if numlist:
            vqobj.image = form.image.data or None
            vqobj.title = form.title.data
            vqobj.calculator_ok = form.calculator_ok.data
            vqobj.shuffle_order = form.shuffle_order.data
            vqobj.vpid_lst = dumps(numlist)
            vqobj.vproblems = [db.session.get(VProblem, a) for a in set(numlist)]
            vqobj.save()
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
    return render_template('vqlist.html', vqlst=vqlst, title='Quizzes', loads=loads)

#route to list a specific virtual quiz
@qgen_bp.route('/quiz/listvq/<vqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vquiz(vqid):
    vqlst = VQuiz.query.filter_by(id=vqid).first_or_404('No VQuiz with id {}'.format(vqid))
    return render_template('vqlist.html', vqlst=[vqlst], title='Quiz {}'.format(vqid), loads=loads)

#route to delete a specific virtual quiz
@qgen_bp.route('/quiz/delvq/<vqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def del_vquiz(vqid):
    vqquery = VQuiz.query.filter_by(id=vqid)
    vq = vqquery.first_or_404('No VQuiz with id {}'.format(vqid))
    title = vq.title
    cq = vq.cquizzes
    if cq:
        estr = 'Quiz "{}" was not deleted because it has been assigned {} time{}. Delete those assignments first.'.format(title, len(cq), '' if len(cq) == 1 else 's')
        current_app.logger.error(estr)
        flash(estr, 'error')
    else:
        vqquery.delete()
        db.session.commit()
        flash('Deleted quiz "{}".'.format(title), 'success')
        current_app.logger.info("{} deleted VQuiz: ({}) '{}'".format(current_user.username, vqid, title))
    return redirect(url_for('qgen.list_vquizzes'))


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
        done = []
        for uid in form.users.data:
            user = db.session.get(User, uid)
            cq = create_cquiz(vquiz, user)
            if cq:
                done.append(user.username)
                current_app.logger.info('{} assigned quiz: "{}" ({}) to {}'.format(current_user.username, vquiz.title, cq.id, user.username))
            else:
                estr = 'Failed to create quiz: "{}" for {}'.format(vquiz.title, user.username)
                flash(estr, 'error')
                current_app.logger.error(estr)
        if done:
            flash('Assigned "{}" to {}.'.format(vquiz.title, ', '.join(done)), 'success')
        return redirect(url_for('qgen.assign'))
    return render_template('assign.html', title='Assign a quiz', form=form)


# ---------------------------------------------------------------- taking

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
    if cq.completed:
        return render_template('transcript.html', cq=cq, title=title, transcript=transcript_html(cq, title))
    if cq.needs_review:
        return render_template('awaiting.html', cq=cq, title=title)
    form = quiz_form_class(cq)()
    if current_user == cq.taker:
        if form.validate_on_submit():
            if record_answers(cq, form):
                cq.needs_review = True
                cq.save()
                current_app.logger.info('{} submitted "{}" ({}) for review'.format(current_user.username, cq.vquiz.title, cidx))
                return redirect(url_for('qgen.qtake', cidx=cidx))
            finalize(cq)
            cq.save()
            current_app.logger.info('{} completed "{}" ({})'.format(current_user.username, cq.vquiz.title, cidx))
            return redirect(url_for('qgen.qtake', cidx=cidx))
        if not cq.startdate:
            cq.startdate = datetime.now()
            current_app.logger.info('{} is starting "{}" ({})'.format(current_user.username, cq.vquiz.title, cidx))
            cq.save()
    elif request.method == 'POST':
        flash("Only {} can submit this quiz.".format(cq.taker.username), 'error')
    return render_template('quiz_take.html', cq=cq, form=form, items=quiz_items(cq, form), title=title,
                           preview=current_user != cq.taker)


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
    essays = [cp for cp in cq.cproblems if not get_qtype(cp.vproblem.qtype).auto_graded]
    form = ReviewForm()
    if request.method == 'GET':
        for cp in essays:
            form.items.append_entry(dict(cpid=cp.id, credit=None if cp.credit is None else round(cp.credit * 100),
                                         feedback=cp.feedback or '', highlights=cp.highlights_json or '[]'))
    elif form.validate_on_submit():
        by_id = {cp.id: cp for cp in essays}
        for item in form.items.data:
            cp = by_id.get(int(item['cpid'] or 0))
            if not cp:
                continue
            cp.credit = None if item['credit'] is None else item['credit'] / 100.0
            cp.feedback = item['feedback'] or None
            try:
                spans = json.loads(item['highlights'] or '[]')
                cp.highlights = [[int(s[0]), int(s[1]), s[2]] for s in spans if s[2] in ('right', 'wrong')]
            except (ValueError, TypeError, IndexError, KeyError):
                cp.highlights = []
        if form.finalize.data:
            ungraded = [cp.ordinal for cp in essays if cp.credit is None]
            if ungraded:
                db.session.commit()
                flash('Give a credit for question{} {} before finishing.'.format('s' if len(ungraded) > 1 else '', ', '.join(map(str, ungraded))), 'error')
                return redirect(url_for('qgen.review', cqid=cq.id))
            cq.graded_by = current_user.id
            cq.graded_date = datetime.now()
            finalize(cq)
            cq.save()
            flash('Finished grading {}\'s "{}": {:.0f}%.'.format(cq.taker.username, cq.vquiz.title, cq.score), 'success')
            current_app.logger.info('{} graded CQuiz ({}) for {}'.format(current_user.username, cq.id, cq.taker.username))
            return redirect(url_for('qgen.review_list'))
        db.session.commit()
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
    return render_template('ulist.html', ulst=ulst, title='Results by student')

#route to list a specific user
@qgen_bp.route('/quiz/listuser/<uid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_user(uid):
    ulst = User.query.filter_by(id=uid).first_or_404('No user with id {}'.format(uid))
    return render_template('ulist.html', ulst=[ulst], title="{}'s quizzes".format(ulst.username))

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
@qgen_bp.route('/quiz/delcq/<cqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def del_cquiz(cqid):
    cqquery = CQuiz.query.filter_by(id=cqid)
    cq = cqquery.first_or_404('No CQuiz with id {}'.format(cqid))
    title = cq.vquiz.title
    owner = cq.taker.username
    CProblem.query.filter_by(cquiz_id=cq.id).delete()
    cqquery.delete()
    db.session.commit()
    flash('Deleted {}\'s "{}".'.format(owner, title), 'success')
    current_app.logger.info("{} deleted {}'s CQuiz: ({}) '{}'".format(current_user.username, owner, cqid, title))
    return redirect(request.referrer or url_for('qgen.list_users'))

#route to reassign a specific concrete quiz to a user (a fresh copy with new values)
@qgen_bp.route('/quiz/retcq/<cqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def ret_cquiz(cqid):
    cq0 = CQuiz.query.filter_by(id=cqid).first_or_404('No CQuiz with id {}'.format(cqid))
    vquiz = VQuiz.query.filter_by(id=cq0.vquiz_id).first()
    user = User.query.filter_by(id=cq0.taker.id).first()
    cq = create_cquiz(vquiz, user)
    if cq:
        flash('Assigned a retake of "{}" to {}.'.format(vquiz.title, user.username), 'success')
        current_app.logger.info('{} assigned retake (of {}) quiz: "{}" ({}) to {}'.format(current_user.username, cqid, vquiz.title, cq.id, user.username))
    else:
        estr = 'Failed to create a retake of "{}" for {}.'.format(vquiz.title, user.username)
        flash(estr, 'error')
        current_app.logger.error(estr)
    return redirect(request.referrer or url_for('qgen.list_users'))


# ---------------------------------------------------------------- AI helper

def ai_fill(kind):
    """Shared by both "Fill in for me" buttons; always answers with JSON."""
    from flask import jsonify
    from datetime import timedelta
    from .ai_helper import ask, problems_with, AIError, HOURLY_LIMIT
    from .models import AICall
    if not json_csrf_ok():
        return jsonify(ok=False, error='Your session expired. Please reload the page.'), 400
    key = current_app.config.get('ANTHROPIC_API_KEY')
    if not key:
        return jsonify(ok=False, error='The AI helper isn\'t set up (no API key).'), 400
    text = ((request.get_json(silent=True) or {}).get('text') or '').strip()
    if not text:
        return jsonify(ok=False, error='Please describe what you want first.'), 400
    if len(text) > 4000:
        return jsonify(ok=False, error='Please keep the description under 4000 characters.'), 400
    since = datetime.now() - timedelta(hours=1)
    if AICall.query.filter(AICall.user_id == current_user.id, AICall.created >= since).count() >= HOURLY_LIMIT:
        return jsonify(ok=False, error='You\'ve used the AI helper {} times in the last hour. Please wait a bit.'.format(HOURLY_LIMIT)), 429
    call = AICall(user_id=current_user.id, created=datetime.now(), kind=kind, request=text, ok=False)
    try:
        fill, usage = ask(key, kind, text)
        call.ok = True
        call.input_tokens, call.output_tokens = usage['input_tokens'], usage['output_tokens']
    except AIError as exc:
        return jsonify(ok=False, error=str(exc)), 502
    finally:
        db.session.add(call)
        db.session.commit()
        current_app.logger.info('{} used the AI helper ({}, ok={}, tokens in/out {}/{})'.format(
            current_user.username, kind, call.ok, call.input_tokens, call.output_tokens))
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
    vpids = parse_vplist(form.vplist.data)
    problems = {p.id: p for p in VProblem.query.filter(VProblem.id.in_(vpids)).all()} if vpids else {}
    vpids = [p for p in vpids if p in problems]
    this_id = request.args.get('vq', type=int)
    others = {q.title.strip().lower() for q in VQuiz.query.all() if q.id != this_id and q.title}
    return jsonify(hints=quiz_hints(form.title.data, vpids, form.calculator_ok.data, others, problems))
