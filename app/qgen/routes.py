from . import db, qgen_bp
from app.user.models import User
from app.user.routes import admin_only, pw_check
from .formfact import quiz_form_class, quiz_items, record_answers, finalize, transcript_html, transcript_item, fieldname_base
from .forms import ProblemForm, QuizForm, AssignForm, ReviewForm
from .models import CQuiz, VQuiz, VProblem, CProblem, VPGroup, VQGroup
from .qtypes import get_qtype, REGISTRY
from .friendly import KINDS, FriendlyError
from . import layout
from app.messages.models import notify
from flask import flash, render_template, redirect, url_for, request, current_app, abort, jsonify
from app.jsoncsrf import json_csrf_ok
from flask_login import current_user, login_required
from re import findall
from json import dumps, loads
from datetime import datetime, timedelta
import json
import random

#generate a concrete problem: this student's own random version
def gen_cprob(cquiz, vprob, ordinal):
    qt = get_qtype(vprob.qtype)
    #problems are checked before saving, but if a rare draw still can't be
    #worked out (e.g. an edge case in an old problem), draw again
    for attempt in range(50):
        try:
            cp, ca, opts = qt.instantiate(vprob.raw_prob, vprob.raw_ansr, vprob.options)
            break
        except FriendlyError:
            if attempt == 49:
                raise FriendlyError('Problem "{}" couldn\'t be set up; please open it and check it.'.format(vprob.title))
    nucprob = CProblem(ordinal=ordinal, cquiz_id=cquiz.id, conc_prob=cp, conc_ansr=ca, vproblem_id=vprob.id)
    nucprob.conc_opts = opts
    return nucprob

def archive(obj, group_cls, rel):
    group = group_cls.query.filter_by(title='Archive').first()
    if group:
        getattr(obj, rel).append(group)

#generate a virtual quiz
def create_vquiz(lst, title, img, calculator_ok, shuffle_order=True, **settings):
    nuquiz = VQuiz(image=img, title=title, vpid_lst=layout.dumps(lst), author_id=current_user.id, calculator_ok=calculator_ok,
                   shuffle_order=shuffle_order, **settings)
    nuquiz.save()
    probs = [VProblem.query.filter_by(id=a).first_or_404('No vproblem with id {}'.format(a)) for a in set(layout.all_ids(lst))]
    nuquiz.vproblems.extend(probs)
    archive(nuquiz, VQGroup, 'vqgroups')
    nuquiz.save()
    return nuquiz

#generate a concrete quiz using virtual and assign to a user
def create_cquiz(vquiz, assignee, opens_at=None, closes_at=None, time_limit=None):
    try:
        nuquiz = CQuiz(vquiz_id=vquiz.id, assignee=assignee.id, opens_at=opens_at, closes_at=closes_at, time_limit=time_limit)
        #groups ("2 of these 6") are drawn separately for each student
        ordered_vids = layout.draw(layout.parse(vquiz.vpid_lst), random)
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
    """The quiz's problem list from the form: single ids and groups."""
    return layout.parse(text)


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
    elif vp.cproblems:
        #students' answers to it are part of their records
        flash('Problem "{}" was not deleted because {} student answer{} to it are on record. '
              'You can take it out of quizzes instead; it just won\'t be used again.'.format(
                  title, len(vp.cproblems), '' if len(vp.cproblems) == 1 else 's'), 'error')
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
    try:
        numlist = parse_vplist(form.vplist.data)
    except layout.LayoutError as exc:
        form.vplist.errors = [str(exc)]
        return None
    if not numlist:
        form.vplist.errors = ['Tick at least one problem.']
        return None
    missing = [n for n in set(layout.all_ids(numlist)) if not db.session.get(VProblem, n)]
    if missing:
        form.vplist.errors = ['These problems no longer exist: {}'.format(', '.join(map(str, missing)))]
        return None
    errors = layout.check(numlist)
    if errors:
        form.vplist.errors = errors
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
            nq = create_vquiz(numlist, form.title.data, form.image.data or None, form.calculator_ok.data, form.shuffle_order.data,
                              retake_rule=form.retake_rule.data, hide_answers=form.hide_answers.data)
            count = layout.question_count(numlist)
            flash('Created quiz "{}": each student gets {} question{}.'.format(nq.title, count, '' if count == 1 else 's'), 'success')
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
        form.vplist.data = layout.dumps(layout.parse(vqobj.vpid_lst))
    elif form.validate_on_submit():
        numlist = checked_vplist(form)
        if numlist:
            vqobj.image = form.image.data or None
            vqobj.title = form.title.data
            vqobj.calculator_ok = form.calculator_ok.data
            vqobj.shuffle_order = form.shuffle_order.data
            vqobj.retake_rule = form.retake_rule.data
            if vqobj.hide_answers != form.hide_answers.data:
                vqobj.answers_released = False
            vqobj.hide_answers = form.hide_answers.data
            vqobj.vpid_lst = layout.dumps(numlist)
            vqobj.vproblems = [db.session.get(VProblem, a) for a in set(layout.all_ids(numlist))]
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


#route to show (or hide again) correct answers on students' results pages
@qgen_bp.route('/quiz/releasevq/<vqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def release_vquiz(vqid):
    vq = db.get_or_404(VQuiz, vqid)
    vq.answers_released = not vq.answers_released
    if vq.answers_released:
        for cq in {c.assignee: c for c in vq.cquizzes if c.completed}.values():
            notify(cq.assignee, 'The correct answers for "{}" are now on your results page.'.format(vq.title),
                   url_for('qgen.qtake', cidx=cq.id))
    vq.save()
    flash('Correct answers for "{}" are now {} to students.'.format(vq.title, 'shown' if vq.answers_released else 'hidden'), 'success')
    return redirect(request.referrer or url_for('qgen.list_vquizzes'))


#route to set how one student's attempts at one quiz combine ('' = use the quiz's rule)
@qgen_bp.route('/quiz/retakerule/<cqid>', methods=['POST'])
@login_required
@pw_check
@admin_only
def set_retake_rule(cqid):
    from .models import RETAKE_RULES
    cq = db.get_or_404(CQuiz, cqid)
    rule = request.form.get('rule') or None
    if rule and rule not in RETAKE_RULES:
        abort(400)
    #kept on every attempt so it survives deleting one
    for other in CQuiz.query.filter_by(assignee=cq.assignee, vquiz_id=cq.vquiz_id):
        other.retake_rule = rule
    db.session.commit()
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
        done = []
        for uid in form.users.data:
            user = db.session.get(User, uid)
            cq = create_cquiz(vquiz, user, form.opens_at.data, form.closes_at.data, form.time_limit.data)
            if cq:
                done.append(user.username)
                when = ' It opens {}.'.format(cq.opens_at.strftime('%b %d at %I:%M %p')) if cq.opens_at else ''
                notify(user.id, 'New quiz: "{}".{}'.format(vquiz.title, when), url_for('qgen.qtake', cidx=cq.id))
                current_app.logger.info('{} assigned quiz: "{}" ({}) to {}'.format(current_user.username, vquiz.title, cq.id, user.username))
            else:
                estr = 'Failed to create quiz: "{}" for {}'.format(vquiz.title, user.username)
                flash(estr, 'error')
                current_app.logger.error(estr)
        db.session.commit()  # the last "new quiz" notice
        if done:
            flash('Assigned "{}" to {}.'.format(vquiz.title, ', '.join(done)), 'success')
        return redirect(url_for('qgen.assign'))
    return render_template('assign.html', title='Assign a quiz', form=form)


# ---------------------------------------------------------------- taking

#answers are still accepted this long after the deadline (slow connections, the auto-submit)
GRACE = timedelta(minutes=2)

def submit_quiz(cq, form=None):
    """Grade and close an attempt, from the submitted form or else from autosaved answers."""
    if record_answers(cq, form):
        cq.needs_review = True
    else:
        finalize(cq)
    cq.save()

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
    now = datetime.now()
    if cq.completed:
        show = cq.vquiz.answers_visible or current_user.is_admin
        return render_template('transcript.html', cq=cq, title=title,
                               transcript=transcript_html(cq, title, show_answers=show), answers_hidden=not show)
    if cq.needs_review:
        return render_template('awaiting.html', cq=cq, title=title)
    if cq.not_open_yet(now) and is_taker:
        return render_template('not_open.html', cq=cq, title=title)
    #out of time: close it with whatever was autosaved
    deadline = cq.deadline()
    if is_taker and deadline and now > deadline + GRACE:
        submit_quiz(cq)
        flash('Time ran out, so your saved answers were submitted.', 'info')
        current_app.logger.info('{} ran out of time on "{}" ({})'.format(current_user.username, title, cidx))
        return redirect(url_for('qgen.qtake', cidx=cidx))
    form = quiz_form_class(cq)()
    if is_taker:
        if form.validate_on_submit():
            submit_quiz(cq, form)
            current_app.logger.info('{} submitted "{}" ({})'.format(current_user.username, title, cidx))
            return redirect(url_for('qgen.qtake', cidx=cidx))
        if not cq.startdate:
            cq.startdate = now
            current_app.logger.info('{} is starting "{}" ({})'.format(current_user.username, title, cidx))
            cq.save()
            deadline = cq.deadline()
    elif request.method == 'POST':
        flash("Only {} can submit this quiz.".format(cq.taker.username), 'error')
    if request.method == 'GET':
        prefill(cq, form)
    return render_template('quiz_take.html', cq=cq, form=form, items=quiz_items(cq, form), title=title,
                           preview=not is_taker, deadline=deadline)

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
    if cq.completed or cq.needs_review:
        return jsonify(ok=False, error='This quiz has already been submitted.'), 409
    deadline = cq.deadline()
    if deadline and datetime.now() > deadline + GRACE:
        return jsonify(ok=False, error='Time is up.'), 409
    form = quiz_form_class(cq)(meta={'csrf': False})
    for cp in cq.cproblems:
        name = fieldname_base.format(cp.ordinal)
        if name in request.form or name + '_present' in request.form:
            cp.submitted = get_qtype(cp.vproblem.qtype).to_stored(form[name].data)
    db.session.commit()
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
            notify(cq.assignee, 'Your written answers in "{}" have been graded: {:.0f}%.'.format(cq.vquiz.title, cq.score),
                   url_for('qgen.qtake', cidx=cq.id))
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
        notify(user.id, 'You can try "{}" again.'.format(vquiz.title), url_for('qgen.qtake', cidx=cq.id))
        db.session.commit()
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
