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
from app.nav import back_to, safe_next, next_arg, place_name, back_after_save, kept_tab, back_to_list
from markupsafe import Markup
from app.jsoncsrf import json_csrf_ok, post_form_only
from flask_login import current_user, login_required
from datetime import datetime, timedelta
import json

def parse_vplist(text):
    """The quiz's problem list from the form: single ids and groups."""
    return layout.parse(text)


# ---------------------------------------------------------------- subjects

LIST_PAGES = {'problems': 'qgen.list_vprobs', 'quizzes': 'qgen.list_vquizzes',
              #(uploads in folders too: the owner, 2026-10-19)
              'pictures': 'upload.images', 'files': 'upload.nonimages'}


def ticked_subjects(item, rel):
    """The subject ids checked on an edit form (as sent, or as saved)."""
    if request.method == 'POST':
        return {int(i) for i in request.form.getlist('subjects') if i.isdigit()}
    return {g.id for g in getattr(item, rel)} if item is not None else set()


def subject_form_error(kind, new):
    """The Folder question on the edit forms: a problem in error only when the new folder's
    name is (choosing a folder is optional: with none, it's in Uncategorized). None when fine."""
    if not request.form.get('subjects_shown'):
        return None
    name = request.form.get('new_subject', '')
    error = S.new_subject_name_error(kind, name)
    if error:
        return error
    #(a new folder goes inside the one folder checked, or at the top with none: the owner 2026-10-16)
    if name.strip() and len(request.form.getlist('subjects')) > 1:
        return 'To make the new folder inside one of your folders, check just that one (or none, to make it at the top).'
    return None


def with_folder_hint(kind, hints, new):
    """The Helper's hints, plus a problem with the Folder question (a bad new folder name);
    then it never says "Looks good"."""
    from .coach import hint
    error = subject_form_error(kind, new)
    if not error:
        return hints
    return [h for h in hints if h['level'] != 'ok'] + [hint('error', error + ' (See “Folder” on this form.)')]


def save_subjects(kind, item):
    """File the item as checked on its form (only forms that show the Subjects row)."""
    if request.form.get('subjects_shown'):
        checked = request.form.getlist('subjects')
        name = ' '.join(request.form.get('new_subject', '').split())
        parent = S.get_subject(kind, checked[0]) if name and len(checked) == 1 else None
        if parent is not None:
            #a new folder with one folder checked: made inside that one, and the item goes in the
            #new folder (the owner, 2026-10-16)
            inner = next((g for g in S.subjects(kind) if g.parent_id == parent.id and (g.title or '').lower() == name.lower()), None)
            S.set_subjects(kind, item, [])
            db.session.commit()
            S.file_items(kind, [item.id], inner or S.create_subject(kind, name, parent))
            return
        S.set_subjects(kind, item, checked)
        db.session.commit()
        if name:
            S.file_items(kind, [item.id], S.subject_named(kind, name))


def subject_page_data(kind, item=None, rel=None, error=None):
    #(just the folders: picking where to file something needs no counts, the owner 2026-10-13)
    return {'subject_kind': kind, 'all_subjects': S.subject_tree(kind, items=[])[1],
            'ticked_subjects': ticked_subjects(item, rel) if rel else set(),
            'subject_error': error, 'new_item': item is None or item.id is None,
            'unsorted_ticked': bool(request.form.get('unsorted')) if request.method == 'POST' else False,
            'new_subject_name': request.form.get('new_subject', '') if request.method == 'POST' else ''}


# ---------------------------------------------------------------- problems

def problem_page(form, vp, errors, title, subject_error=None, same=None):
    #unbound copy with one empty row of each kind, cloned by problem_form.js for "+ Add"
    blank = ProblemForm(formdata=None)
    blank.values.append_entry()
    blank.images.append_entry()
    return render_template('problem_form.html', form=form, vp=vp, errors=errors, title=title, blank=blank,
                           kinds=KINDS, qtypes=REGISTRY, same=same, ai_enabled=bool(current_app.config.get('ANTHROPIC_API_KEY')),
                           **subject_page_data('problems', vp, 'vpgroups', subject_error))

def save_from_form(form, vp):
    options = form.options()
    #a problem made from a scanned page keeps how its words are written over the page, while its
    #values are still there (the owner, 2026-10-18)
    kept = (vp.options or {}).get('page_text') if vp.id is not None else None
    if kept and options['values'] and S.page_text_fits(kept, options['values']):
        options['page_text'] = kept
    return S.save_problem(vp, form.qtype.data, form.title.data, form.question.data, form.answer.data,
                          options, form.calculator_ok.data)

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
        #the same as a problem already there: said once; Save again saves it anyway (the owner, 2026-10-18)
        same = None
        if not subject_error and not request.form.get('same_ok') and not S.problem_errors(
                form.qtype.data, form.question.data, form.answer.data, form.options()):
            same = S.same_problem(form.qtype.data, form.question.data, form.answer.data, form.options())
        if same is not None:
            return problem_page(form, None, [], 'New problem', same=same)
        errors = [subject_error] if subject_error else save_from_form(form, nuprob)
        if not errors:
            save_subjects('problems', nuprob)
            flash('Saved problem “{}”.'.format(nuprob.title), 'success')
            current_app.logger.info('{} created VProblem: ({}) "{}"'.format(current_user.username, nuprob.id, nuprob.title))
            return redirect(back_after_save('qgen.list_vprobs', nuprob.id, new=True))
    elif request.method == 'GET' and not form.values.entries:
        form.values.append_entry()
    return problem_page(form, None, errors, 'New problem', subject_error)

#one problem's History: every handed-in answer to it, in whatever quiz, by quiz
@qgen_bp.route('/quiz/problem-results/<int:vpid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def problem_results(vpid):
    from collections import Counter
    from .models import CProblem
    vp = db.session.get(VProblem, vpid)
    if vp is None:
        return gone('That problem has been deleted.', url_for('qgen.list_vprobs'))
    cps = (CProblem.query.filter(CProblem.vproblem_id == vp.id).join(CQuiz, CProblem.cquiz_id == CQuiz.id)
           .filter(db.or_(CQuiz.completed.is_(True), CQuiz.needs_review.is_(True))).all())
    rows = [{'cp': cp, 'cq': cp.cquiz, 'student': cp.cquiz.taker, 'item': transcript_item(cp)} for cp in cps]
    rows.sort(key=lambda r: ((r['student'].username.lower() if r['student'] else ''), r['cq'].compdate or datetime.min))
    by_quiz = {}
    for r in rows:
        by_quiz.setdefault(r['cq'].vquiz, []).append(r)
    quizzes = sorted(by_quiz.items(), key=lambda kv: (kv[0].title or '').lower())
    graded = [r['cp'].credit for r in rows if r['cp'].credit is not None]
    summary = {'tries': len(rows), 'students': len({r['student'].id for r in rows if r['student']}),
               'average': 100.0 * sum(graded) / len(graded) if graded else None,
               'right': sum(1 for c in graded if c == 1), 'waiting': len(rows) - len(graded)}
    #when everyone gets the same numbers, the same wrong answers are worth seeing together
    common = []
    qt = get_qtype(vp.qtype)
    if qt.auto_graded and not vp.options.get('values'):
        wrong = Counter(' '.join((r['item'].submitted or '').split()) for r in rows
                        if r['cp'].credit is not None and r['cp'].credit < 1 and (r['item'].submitted or '').strip())
        common = [(answer, n) for answer, n in wrong.most_common(5) if n > 1]
    #the quizzes in the Quizzes page's folders, like Grading (the owner, 2026-10-17)
    from app import folder_tree
    vqs = [vq for vq, _rows in quizzes]
    answers = {vq.id: r for vq, r in quizzes}
    root, flat, nodes = S.subject_tree('quizzes', items=vqs)
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='all')
    shown = node['items'] if node else vqs if view == 'all' else root['items']
    fk = folder_tree.kit(
        view, node, root, flat, nodes, readonly=True,
        page=lambda v: url_for('qgen.problem_results', vpid=vp.id, folder=v),
        unit='quiz', units='quizzes', all_label='All quizzes', all_count=len(vqs), name=lambda f: f.title,
        hint=Markup('The <a href="{}">Quizzes page</a>\'s folders: make and fill them there.').format(url_for('qgen.list_vquizzes')),
        fold_key='qgen-folded-problem-results-folders')
    return render_template('problem_results.html', vp=vp, qt=qt, quizzes=quizzes, answers=answers, shown=shown, fk=fk,
                           summary=summary, common=common, title='Problem history: {}'.format(vp.title or 'Untitled'))

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
            flash('Updated problem “{}”. Quizzes already assigned keep the version they were given.'.format(vpobj.title), 'success')
            current_app.logger.info('{} updated VProblem: ({}) "{}"'.format(current_user.username, vpobj.id, vpobj.title))
            return redirect(back_after_save('qgen.list_vprobs', vpobj.id))
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

#checked problems (or one row's) added to the end of a quiz the teacher picks, from the
#Problems page; ones already in it are left where they are (the owner, 2026-10-15)
@qgen_bp.route('/quiz/addtoquiz', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def add_to_quiz():
    quizzes = [q for q in (VQuiz.query.filter_by(id=int(x)).first() for x in dict.fromkeys(request.form.getlist('quiz')) if x.isdigit())
               if q and not q.removed_at]
    if not quizzes:
        return _subject_done('problems', 'Check at least one quiz first.', error=True)
    ids = []
    for x in request.form.getlist('items'):
        if x.isdigit() and int(x) not in ids and db.session.get(VProblem, int(x)):
            ids.append(int(x))
    if not ids:
        return _subject_done('problems', 'Check at least one first.', error=True)
    said, problems = [], []
    for vq in quizzes:
        lay = layout.parse(vq.vpid_lst)
        there = set(layout.all_ids(lay))
        new = [i for i in ids if i not in there]
        if not new:
            said.append('{} already in “{}”.'.format('It’s' if len(ids) == 1 else 'They’re all', vq.title))
            continue
        lay, errors = S.check_layout(lay + new)
        if errors:
            problems.append('“{}”: {}'.format(vq.title, ' '.join(errors)))
            continue
        vq.vpid_lst = layout.dumps(lay)
        current_app.logger.info('{} added problems {} to VQuiz ({}) "{}"'.format(current_user.username, new, vq.id, vq.title))
        skipped = len(ids) - len(new)
        said.append('Added {} problem{} to “{}”{}.'.format(len(new), '' if len(new) == 1 else 's', vq.title,
                    ' ({} already in it)'.format(skipped) if skipped else ''))
    db.session.commit()
    for p_ in problems:
        flash(p_, 'error')
    if not said:
        return _subject_done('problems', 'Nothing was added.', error=True)
    return _subject_done('problems', ' '.join(said) + ' Quizzes already assigned keep the version they were given.')


#route to list all virtual problems
@qgen_bp.route('/quiz/listvp', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vprobs():
    return subject_page('problems', 'vplist.html', qtypes=REGISTRY, title='Problems', all_subjects=S.subject_tree('problems')[1],
                        quizzes=VQuiz.query.filter(VQuiz.removed_at.is_(None)).order_by(VQuiz.title).all(),
                        archived=S.archived_counts()[1], archive_warning=S.archive_warning)

#one problem: its row on the Problems page, opened and lit up (old links and notices lead here)
@qgen_bp.route('/quiz/listvp/<vpid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vprob(vpid):
    vp = VProblem.query.filter_by(id=vpid).first_or_404('No vproblem with id {}'.format(vpid))
    return redirect(url_for('qgen.list_vprobs', show=vp.id))

#route to delete a specific virtual problem
@qgen_bp.route('/quiz/delvp/<vpid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def del_vprob(vpid):
    vp = VProblem.query.filter_by(id=vpid).first_or_404('No VProblem with id {}'.format(vpid))
    title = vp.title
    #(one a quiz uses, or students answered, is kept for those and quietly taken off the page)
    how = S.delete_problem(vp)
    flash('Deleted problem “{}”.'.format(title) if how == 'deleted' else
          'Deleted problem “{}” from Problems; the quizzes that use it keep it.'.format(title), 'success')
    current_app.logger.info("{} deleted VProblem: ({}) '{}'".format(current_user.username, vpid, title))
    return redirect(back_to_list('qgen.list_vprobs'))


#the trash can's Move to Archive (the owner, 2026-10-16): off the Problems page, kept in the
#Archive's Problems, where it can be restored
@qgen_bp.route('/quiz/archivevp/<int:vpid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def archive_vprob(vpid):
    vp = db.session.get(VProblem, vpid)
    if vp is None:
        return gone('That problem has been deleted.', url_for('qgen.list_vprobs'))
    S.archive_problem(vp)
    flash(Markup('Moved problem “{}” to the <a href="{}">Archive</a>, where you can restore it.').format(
        vp.title, url_for('qgen.archive', section='problems')), 'success')
    current_app.logger.info("{} archived VProblem: ({}) '{}'".format(current_user.username, vpid, vp.title))
    return redirect(back_to_list('qgen.list_vprobs'))


@qgen_bp.route('/quiz/restorevp/<int:vpid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def restore_vprob(vpid):
    vp = db.session.get(VProblem, vpid)
    if vp is None:
        return gone('That problem has been deleted.', url_for('qgen.archive', section='problems'))
    S.restore_problem(vp)
    flash('“{}” is back on the Problems page.'.format(vp.title), 'success')
    return redirect(url_for('qgen.archive', section='problems'))


# ---------------------------------------------------------------- quizzes

def quiz_page(form, title, vq=None, subject_error=None):
    #the problems to pick from: one list, each once (newest first), with the Problems page's
    #folders as tabs over it (static/js/folderfilter.js), like every folder page
    from app import folder_tree
    #(a problem taken off the Problems page that this quiz still uses stays in its list, so
    #saving the quiz keeps it)
    items = S.in_use('problems').order_by(VProblem.id.desc()).all()
    if vq is not None:
        items += [p for p in vq.vproblems if p.removed_at is not None]
    root = S.subject_tree('problems', items=items)[0]
    problem_tree = folder_tree.filter_tree(root, lambda f: f.title, lambda fid: None, 'p:')
    all_problems = sorted(folder_tree.subtree(root), key=lambda p: p.id, reverse=True)
    return render_template('quiz_form.html', form=form, title=title, problem_root=root,
                           problem_tree=problem_tree, all_problems=all_problems,
                           has_problems=bool(all_problems), qtypes=REGISTRY, vq=vq,
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
    #from the Problems page's Add to a quiz dialog: these problems already in it (?problems=4,7;
    #its Back goes back there, ?next=: the owner, 2026-10-15)
    if request.method == 'GET' and request.args.get('problems'):
        ids = [int(x) for x in request.args['problems'].split(',') if x.isdigit()]
        ids = [i for i in dict.fromkeys(ids) if (lambda p: p is not None and not p.removed_at)(db.session.get(VProblem, i))]
        if ids:
            form.vplist.data = json.dumps(ids)
    if form.validate_on_submit():
        nq = VQuiz()
        subject_error = subject_form_error('quizzes', new=True)
        if not subject_error and not save_quiz_from_form(form, nq):
            save_subjects('quizzes', nq)
            count = layout.question_count(layout.parse(nq.vpid_lst))
            #(with a link that opens the Assign dialog for it, static/js/assign_many.js; the Assign
            #page where there's no dialog: the owner, 2026-10-16)
            flash(Markup('Created quiz “{}”: each student gets {} question{}. <a href="{}" data-what="“{}”" title="Give “{}” to students">Assign it now →</a>').format(
                nq.title, count, '' if count == 1 else 's', url_for('qgen.assign', vq=nq.id), nq.title, nq.title), 'success')
            current_app.logger.info('{} created VQuiz: ({}) "{}"'.format(current_user.username, nq.id, nq.title))
            return redirect(back_after_save('qgen.list_vquizzes', nq.id, new=True))
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
    return render_template('view_quiz.html', vq=vq, items=items, error=error, title='View: {}'.format(vq.title),
                           varies=S.quiz_varies(vq) if not error else True)

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
            flash('Updated quiz “{}”. Quizzes already assigned keep the version they were given.'.format(vqobj.title), 'success')
            if vqobj.retake_rule != old_rule and had_own:
                flash('The new retake scoring now applies to every student, including the {} who had {} own.'.format(
                    'one' if had_own == 1 else had_own, 'his/her' if had_own == 1 else 'their'), 'success')
            current_app.logger.info('{} updated VQuiz: ({}) "{}"'.format(current_user.username, vqobj.id, vqobj.title))
            return redirect(back_after_save('qgen.list_vquizzes', vqobj.id))
    return quiz_page(form, 'Edit quiz', vqobj, subject_error)

#the checked quizzes given to the people picked in the Quizzes page's Assign quizzes dialog:
#each opens now, with no closing time or time limit (the Assign page sets those), the owner
#2026-10-15
@qgen_bp.route('/quiz/assignmany', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def assign_many():
    #(sent from People: back there, ?next=; else the Quizzes page, as it was)
    then = safe_next(request.form.get('next'))
    def done_(message, error=False):
        if not then:
            return _subject_done('quizzes', message, error=error)
        flash(message, 'error' if error else 'success')
        return redirect(then)
    qids = list(dict.fromkeys(int(x) for x in request.form.getlist('items') if x.isdigit()))
    uids = list(dict.fromkeys(int(x) for x in request.form.getlist('users') if x.isdigit()))
    quizzes = [q for q in (db.session.get(VQuiz, i) for i in qids) if q and not q.removed_at]
    students = [u for u in (db.session.get(User, i) for i in uids) if u]
    if not quizzes:
        return done_('Check at least one quiz first.', error=True)
    if not students:
        return done_('Check at least one person to assign them to.', error=True)
    done, paper = [], []
    for vq in quizzes:
        created, failed = S.assign(vq, students, by=current_user)
        for student, err in failed:
            flash(err, 'error')
            current_app.logger.error(err)
        for cq in created:
            current_app.logger.info('{} assigned quiz: "{}" ({}) to {}'.format(current_user.username, vq.title, cq.id, cq.taker.username))
        if created:
            done.append(vq)
            if paper_problems(vq):
                paper.append((vq, [cq.taker.id for cq in created]))
    for vq, users in paper:
        flash(Markup('“{}” has pages done on paper: <a href="{}">print a copy for each of them</a>.').format(
            vq.title, url_for('qgen.print_paper', vqid=vq.id, users=users)), 'success')
    if not done:
        return done_('Nothing was assigned.', error=True)
    return done_('Assigned {} to {}.'.format(', '.join('“{}”'.format(q.title) for q in done),
                                                                ', '.join(u.shown_name for u in students)))


#route to list all virtual quizzes
@qgen_bp.route('/quiz/listvq', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vquizzes():
    return subject_page('quizzes', 'vqlist.html', title='Quizzes', layout=layout, rules=RETAKE_RULES,
                        all_subjects=S.subject_tree('quizzes')[1], archived=S.archived_counts()[0], archive_warning=S.archive_warning,
                        removed_count=len(S.removed_quizzes()))

#one quiz: its row on the Quizzes page, opened and lit up (old links and notices lead here)
@qgen_bp.route('/quiz/listvq/<vqid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_vquiz(vqid):
    vq = VQuiz.query.filter_by(id=vqid).first() if str(vqid).isdigit() else None
    if vq is None:
        return gone('That quiz has been deleted.', url_for('qgen.list_vquizzes'))
    if vq.removed_at:  # not on Quizzes: the Removed quizzes page, where it can be restored
        return redirect(url_for('qgen.archive', section='quizzes'))
    return redirect(url_for('qgen.list_vquizzes', show=vq.id))

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
        done = S.delete_vquiz(vq)
    except S.ServiceError as exc:
        flash('Not removed. {}'.format(exc), 'error')
        return redirect(back_to(url_for('qgen.list_vquizzes')))
    if done == 'removed':
        flash(Markup('Removed “{}” from Quizzes. Students keep their copies and scores, and its results stay. '
                     'You can restore it from the <a href="{}">Archive</a>.').format(title, url_for('qgen.archive', section='quizzes')), 'success')
    else:
        flash('Deleted quiz “{}”.'.format(title), 'success')
    #(logged either way, with the page it came from, so where it went back to can be checked)
    current_app.logger.info("{} {} VQuiz: ({}) '{}' from {}".format(current_user.username, done, vqid, title, request.referrer))
    return redirect(back_to_list('qgen.list_vquizzes'))


#a row's Copy icon, from its dialog (static/js/copy.js; the owner, 2026-10-16): a copy with the
#name typed there, in the same folders, then opened in its editor
@qgen_bp.route('/quiz/copy/<kind>/<int:iid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def copy_item(kind, iid):
    if kind not in LIST_PAGES:
        abort(404)
    item = db.session.get(S.subject_kind(kind)[1], iid)
    if item is None:
        return gone('That {} has been deleted.'.format('problem' if kind == 'problems' else 'quiz'), url_for(LIST_PAGES[kind]))
    if kind == 'quizzes':
        #(two quizzes may not share a name: the owner, 2026-10-19)
        name = ' '.join((request.form.get('title', '') or item.title).split())[:64]
        if S.quiz_name_taken(name):
            flash(S.QUIZ_NAME_TAKEN.format(name), 'error')
            return redirect(back_to(url_for(LIST_PAGES[kind])))
    new = S.copy_item(kind, item, request.form.get('title', ''), current_user)
    current_app.logger.info('{} copied {} {} to {} "{}"'.format(current_user.username, kind, iid, new.id, new.title))
    #(straight to the new copy, open in its editor: the owner, 2026-10-16)
    flash('Made “{}”, a copy of “{}”. Change what you like, then save.'.format(new.title, item.title), 'success')
    return redirect(url_for('qgen.edvprob', vpid=new.id) if kind == 'problems' else url_for('qgen.edvquiz', vqid=new.id))


#the checked bar's Restore in the Archive's Problems, Quizzes and People (the owner, 2026-10-16)
@qgen_bp.route('/quiz/archive/restore/<kind>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def restore_many(kind):
    ids = [int(i) for i in request.form.getlist('items') if str(i).isdigit()]
    n, kept = 0, []
    if kind == 'people':
        from app.user.accounts import any_person, restore_account
        for uid in ids:
            usr = any_person(uid)
            if usr is not None and usr.archived_at:
                restore_account(usr)
                n += 1
        word = 'person' if n == 1 else 'people'
    elif kind in ('problems', 'quizzes'):
        item_cls = S.subject_kind(kind)[1]
        for item in item_cls.query.filter(item_cls.id.in_(ids), item_cls.removed_at.isnot(None)).all() if ids else []:
            if kind == 'quizzes' and S.quiz_name_taken(item.title, item.id):
                kept.append(item.title)  # (two quizzes may not share a name: the owner, 2026-10-19)
                continue
            (S.restore_problem if kind == 'problems' else S.bring_back_vquiz)(item)  # (in Uncategorized)
            n += 1
        word = _item_word(kind, n)
        if kept:
            flash('Not restored: {}. There’s already a quiz by that name on the Quizzes page; rename that one first.'.format(
                ', '.join('“{}”'.format(t) for t in kept)), 'error')
    else:
        abort(404)
    #(none restored because every one clashed: only the "Not restored" message, not "Restored 0"
    #beside it: from the code critic, 2026-10-19)
    if n or not kept:
        flash('Restored {} {}.'.format(n, word), 'success')
    view = request.form.get('view')
    return redirect(url_for('qgen.archive', section=kind, **({'folder': view} if view else {})))


#the trash can's Move to Archive for a quiz, taken or not (the owner, 2026-10-16)
@qgen_bp.route('/quiz/archivevq/<int:vqid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def archive_vquiz(vqid):
    vq = db.session.get(VQuiz, vqid)
    if vq is None:
        return gone('That quiz has been deleted.', url_for('qgen.list_vquizzes'))
    try:
        S.archive_vquiz(vq)
    except S.ServiceError as exc:
        flash('Not archived. {}'.format(exc), 'error')
        return redirect(back_to(url_for('qgen.list_vquizzes')))
    flash(Markup('Moved quiz “{}” to the <a href="{}">Archive</a>, where you can restore it. Students keep their copies and scores.').format(
        vq.title, url_for('qgen.archive', section='quizzes')), 'success')
    current_app.logger.info("{} archived VQuiz: ({}) '{}'".format(current_user.username, vqid, vq.title))
    return redirect(back_to_list('qgen.list_vquizzes'))


#route to the quizzes taken off the Quizzes page: bring one back, or delete it for good once
#nobody has a copy
@qgen_bp.route('/quiz/removed', methods=['GET'])
@login_required
@pw_check
@admin_only
def removed_vquizzes():
    #(the warning the quiz's Delete gave before there was a trash bin: archived attempts use it)
    #(now the Archive's Quizzes section, the owner 2026-10-16)
    return redirect(url_for('qgen.archive', section='quizzes'))


@qgen_bp.route('/quiz/removed/<int:vqid>/delete', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delete_removed_vquiz(vqid):
    vq = db.session.get(VQuiz, vqid)
    if vq is None:
        return gone('That quiz has been deleted.', url_for('qgen.archive', section='quizzes'))
    title = vq.title
    try:
        count = S.delete_removed_vquiz(vq, by=current_user)
    except S.ServiceError as exc:
        flash('Not deleted. {}'.format(exc), 'error')
        return redirect(url_for('qgen.archive', section='quizzes'))
    if count:
        flash(Markup('Deleted “{}” for good. Its {} {} in the <a href="{}">Archive</a>, where you can still read {}.').format(
            title, count, 'attempt is' if count == 1 else 'attempts are', url_for('qgen.archive'), 'it' if count == 1 else 'them'), 'success')
    else:
        flash('Deleted “{}” for good.'.format(title), 'success')
    current_app.logger.info("{} deleted removed VQuiz: ({}) '{}', {} tries archived".format(current_user.username, vqid, title, count))
    return redirect(url_for('qgen.archive', section='quizzes'))


@qgen_bp.route('/quiz/removed/<int:vqid>/back', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def bring_back_vquiz(vqid):
    vq = db.session.get(VQuiz, vqid)
    if vq is None:
        return gone('That quiz has been deleted.', url_for('qgen.archive', section='quizzes'))
    if S.quiz_name_taken(vq.title, vq.id):
        #(two quizzes may not share a name: the owner, 2026-10-19)
        flash('There’s already a quiz called “{}” on the Quizzes page. Rename that one first, then restore this one.'.format(vq.title), 'error')
        return redirect(url_for('qgen.archive', section='quizzes'))
    S.bring_back_vquiz(vq)
    flash('“{}” is back on the Quizzes page.'.format(vq.title), 'success')
    current_app.logger.info("{} brought back VQuiz: ({}) '{}'".format(current_user.username, vqid, vq.title))
    return redirect(url_for('qgen.list_vquizzes', show=vq.id))


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
    flash('{}\'s score for “{}” is now: {}.'.format(cq.taker.shown_name, cq.vquiz.title,
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
    quizzes = S.in_use('quizzes').order_by(VQuiz.title).all()
    form.vquiz.choices = [(q.id, q.title) for q in quizzes]
    form.users.choices = [(u.id, u.username) for u in User.query.order_by(User.username).all()]
    #a link for one quiz opens on All, so that quiz is in the list
    choice = 'all' if request.args.get('vq', '').isdigit() else S.valid_subject_choice('quizzes', request.args.get('subject', 'all'))
    #(one that's been removed isn't in the list: then the first quiz, as with no link)
    if request.method == 'GET' and request.args.get('vq', '').isdigit() and int(request.args['vq']) in {q.id for q in quizzes}:
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
            flash(Markup('Assigned “{}” to {}. <a href="{}">View the quiz</a> · <a href="{}">See its history →</a>').format(
                vquiz.title, ', '.join(cq.taker.shown_name for cq in created), url_for('qgen.view_vquiz', vqid=vquiz.id),
                url_for('qgen.quiz_results_page', vqid=vquiz.id)), 'success')
        #back where they came from (a student page, a quiz's results...), else ready for the next one
        then = next_arg(url_for('qgen.assign'))
        if created and paper_problems(vquiz):
            #pages done on paper: straight to printing a copy for each of them
            return redirect(url_for('qgen.print_paper', vqid=vquiz.id, users=[cq.taker.id for cq in created], next=then))
        return redirect(then)
    #the quizzes to pick from: one list (A to Z) with the Quizzes page's folders down its side,
    #like the students beside it (static/js/folderfilter.js); ?subject= opens on that folder
    from app import folder_tree
    quiz_root = S.subject_tree('quizzes', items=quizzes)[0]
    quiz_tree = folder_tree.filter_tree(quiz_root, lambda f: f.title, lambda fid: None, 'quiz:')
    quiz_start = choice
    #(opened for one quiz, e.g. View's paper plane: on that quiz's own folder, its first one A to Z,
    #or Uncategorized when it's in none, so it's in sight: the owner, 2026-10-19)
    if request.args.get('vq', '').isdigit() and request.method == 'GET':
        came = db.session.get(VQuiz, int(request.args['vq']))
        if came is not None:
            homes = sorted(came.vqgroups, key=lambda g: (g.title or '').lower())
            quiz_start = str(homes[0].id) if homes else 'none'
    #nothing picked yet: the first quiz, as the menu had it
    if form.vquiz.data is None and quizzes:
        form.vquiz.data = quizzes[0].id
    #the people to choose from: one checklist with the People folders as tabs over it, like every
    #folder page (static/js/folderfilter.js); from People, some come already checked (?users=...,
    #or everyone in ?folder=, which opens on that folder's tab)
    from app.user import groups
    people = User.query.order_by(User.username).all()
    root, _, nodes, folders_of = groups.tree(people)
    chosen, start = set(form.users.data or []), 'all'
    if request.method == 'GET':
        chosen = {int(u) for u in request.args.getlist('users') if u.isdigit()} & {u.id for u in people}
        folder = request.args.get('folder', '')
        if folder.isdigit() and int(folder) in nodes:
            chosen |= nodes[int(folder)]['everyone']
            start = folder
    pick_tree = folder_tree.filter_tree(root, lambda f: f.name, lambda fid: None, 'user:')
    #the page they came from, when it's one to go back to (the Assign page itself isn't)
    from app.nav import back
    target = request.form.get('next') if request.method == 'POST' else None
    came_from = back(None, None) if not target else (safe_next(target), place_name(safe_next(target)))
    came_from = came_from if came_from and came_from[0] and came_from[1] else None
    return render_template('assign.html', title='Assign a quiz', form=form, came_from=came_from,
                           quizzes=quizzes, quiz_tree=quiz_tree, quiz_start=quiz_start,
                           people=people, root=root, chosen=chosen, pick_tree=pick_tree, pick_start=start)


def paper_problems(vquiz):
    """The quiz's Paper only problems, in quiz order (every one in a pick-from group too,
    since a student's picks aren't drawn until they start), each once."""
    probs = {p.id: p for p in vquiz.vproblems}
    ids = dict.fromkeys(i for i in layout.all_ids(layout.parse(vquiz.vpid_lst)) if i in probs)
    return [probs[i] for i in ids if get_qtype(probs[i].qtype).paper]


@qgen_bp.route('/quiz/print/<int:vqid>')
@login_required
@pw_check
@admin_only
def print_paper(vqid):
    """The quiz's paper pages, one copy per student with their name on top; the print
    dialog opens by itself."""
    vquiz = db.get_or_404(VQuiz, vqid)
    ids = [int(u) for u in request.args.getlist('users') if u.isdigit()]
    students = [u for u in (db.session.get(User, i) for i in dict.fromkeys(ids)) if u]
    then = next_arg(url_for('qgen.quiz_results_page', vqid=vquiz.id))
    return render_template('print_paper.html', title='Print: ' + vquiz.title, vquiz=vquiz, pages=paper_problems(vquiz),
                           students=students or [None], then=then, then_name=place_name(then), today=datetime.now())


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
    #their quiz page is on screen (the Dashboard's "Taking a quiz"; its check-ins keep it so)
    if is_taker:
        from app.user.models import note_page
        note_page(current_user, 'attempt:{}'.format(cq.id))
    #opened from Home or a notice: no longer new (the count beside "My quizzes" goes down)
    if is_taker and not cq.seen_by_taker:
        cq.seen_by_taker = True
        db.session.commit()
    state = S.attempt_state(cq)
    if state == 'completed':
        return render_template('transcript.html', cq=cq, title=title, transcript=transcript_html(cq, title))
    if state == 'review':
        return render_template('awaiting.html', cq=cq, title=title)
    if state == 'not_open' and is_taker:
        return render_template('not_open.html', cq=cq, title=title)
    #out of time: close it with whatever was autosaved
    if state == 'time_up' and is_taker:
        S.submit(cq)
        flash('Time ran out, so your answers were handed in.', 'info')
        current_app.logger.info('{} ran out of time on "{}" ({})'.format(current_user.username, title, cidx))
        return redirect(url_for('qgen.qtake', cidx=cidx))
    #not started yet: a card saying what's ahead; nothing starts (nor its timer) until "Start the quiz"
    if is_taker and not cq.startdate and request.method == 'GET':
        now = datetime.now()
        #a close time sooner than the time limit cuts the time short
        cut_short = bool(cq.time_limit and cq.closes_at and cq.closes_at < now + timedelta(minutes=cq.time_limit))
        return render_template('quiz_start.html', cq=cq, title=title, count=len(cq.cproblems), cut_short=cut_short)
    form = quiz_form_class(cq)()
    if is_taker:
        if form.validate_on_submit():
            S.submit(cq, form_answers(cq, form))
            current_app.logger.info('{} submitted "{}" ({})'.format(current_user.username, title, cidx))
            return redirect(url_for('qgen.qtake', cidx=cidx))
        if request.method == 'POST' and form.csrf_token.errors:
            #(never silent: the answers sent are still filled in below, to hand in again)
            flash('Your quiz wasn’t handed in. Your answers are still here: press Hand it in again.', 'error')
        if not cq.startdate:
            S.start(cq)
            current_app.logger.info('{} is starting "{}" ({})'.format(current_user.username, title, cidx))
    elif request.method == 'POST':
        flash("Only {} can submit this quiz.".format(cq.taker.shown_name), 'error')
    if request.method == 'GET':
        prefill(cq, form)
    return render_template('quiz_take.html', cq=cq, form=form, items=quiz_items(cq, form), title=title,
                           preview=not is_taker, deadline=cq.deadline(), page_layout=page_layout(cq.vquiz, cq),
                           page_opts={cp.ordinal: cp.conc_opts for cp in cq.cproblems})


#how a covered problem's words are set on its page (pagelayout.style_of): for quiz_take.html
@qgen_bp.app_template_filter('pq_style')
def pq_style(words):
    from .pagelayout import style_of
    return style_of(words)


@qgen_bp.app_template_filter('pq_no_blank')
def pq_no_blank(words):
    """A problem's words without the "???" (or "___") at the very end, where the answer box goes."""
    import re
    return re.sub(r'\s*(\?{2,}|_{3,}|\?)\s*$', '', words)


def page_layout(vq, cq=None):
    """A quiz made from a scanned page is taken on the page itself (pagelayout.py, the owner,
    2026-10-18): its layout, with each slot under its question number, or None to take it
    the usual way. That's also so when the quiz was changed after it was made (other
    problems, or a shuffled order), since the page then no longer matches it."""
    from . import layout as quiz_layout
    L = vq.page_layout
    if not L or vq.shuffle_order or quiz_layout.parse(vq.vpid_lst) != L.get('ids'):
        return None
    if cq is not None and len(cq.cproblems) != len(L['ids']):
        return None
    L['by_pos'] = {s['pos']: s for s in L['slots']}
    return L


#"Start the quiz" on the start card: the quiz (and its time limit) starts now
@qgen_bp.route('/quiz/take/<int:cidx>/start', methods=['POST'])
@login_required
@pw_check
@post_form_only
def start_quiz(cidx):
    cq = db.session.get(CQuiz, cidx)
    if cq is None:
        return attempt_gone(cidx)
    if current_user == cq.taker and S.attempt_state(cq) == 'open' and not cq.startdate:
        S.start(cq)
        current_app.logger.info('{} is starting "{}" ({})'.format(current_user.username, cq.vquiz.title, cidx))
    return redirect(url_for('qgen.qtake', cidx=cidx))

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
    from app import push
    push.not_me()
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
    #grouped by quiz, in the Quizzes page's folders, like Results by quiz (the owner, 2026-10-17)
    from app import folder_tree
    waiting = waiting_for_grading()
    quizzes, by_quiz = [], {}
    for cq in waiting:
        if cq.vquiz_id not in by_quiz:
            by_quiz[cq.vquiz_id] = []
            quizzes.append(cq.vquiz)
        by_quiz[cq.vquiz_id].append(cq)
    root, flat, nodes = S.subject_tree('quizzes', items=quizzes)
    #(the folders count attempts waiting, not quizzes: the owner, 2026-10-19)
    weight = {q.id: len(by_quiz[q.id]) for q in quizzes}
    def weigh(n):
        n['count'] = sum(weight.get(k, 0) for k in n['everyone'])
        for c in n['folders']:
            weigh(c)
    for c in root['folders']:
        weigh(c)
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='all')
    shown = node['items'] if node else quizzes if view == 'all' else root['items']
    fk = folder_tree.kit(
        view, node, root, flat, nodes, readonly=True,
        page=lambda v: url_for('qgen.review_list', folder=v),
        unit='quiz', units='quizzes', count_unit='attempt', count_units='attempts',
        main_count=sum(weight.get(q.id, 0) for q in root['items']),
        all_label='All quizzes', all_count=len(waiting), name=lambda f: f.title,
        hint=Markup('The <a href="{}">Quizzes page</a>\'s folders: make and fill them there.').format(url_for('qgen.list_vquizzes')),
        fold_key='qgen-folded-grading-folders')
    return render_template('review_list.html', waiting=waiting, by_quiz=by_quiz, shown=shown, fk=fk, title='Grading')

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
    #where Finish grading goes back to: the page whose Grade button opened this (a quiz's or a
    #problem's results, the Dashboard); the Grading list when it was that, a notice or unknown
    #(the owner, 2026-10-16). Kept through Save draft as ?back=
    back = safe_next(request.values.get('back')) or (safe_next(request.referrer) if request.method == 'GET' else None)
    if back and back.split('?')[0].rstrip('/').startswith(('/quiz/review', '/messages', '/login')):
        back = None
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
            return redirect(url_for('qgen.review', cqid=cq.id, back=back))
        if ungraded:
            flash('Give a credit for question{} {} before finishing.'.format('s' if len(ungraded) > 1 else '', ', '.join(map(str, ungraded))), 'error')
            return redirect(url_for('qgen.review', cqid=cq.id, back=back))
        if finish:
            flash('Finished grading {}\'s “{}”: {:.0f}%.'.format(cq.taker.shown_name, cq.vquiz.title, cq.score), 'success')
            current_app.logger.info('{} graded CQuiz ({}) for {}'.format(current_user.username, cq.id, cq.taker.username))
            after = waiting_for_grading()
            if form.finalize_next.data and after:
                return redirect(url_for('qgen.review', cqid=after[0].id))
            if form.finalize_next.data:
                flash('That was the last one: nothing else is waiting for grading.', 'success')
                return redirect(url_for('qgen.review_list'))
            return redirect(back or url_for('qgen.review_list'))
        flash('Draft saved.', 'success')
        return redirect(url_for('qgen.review', cqid=cq.id, back=back))
    entries = {int(e.form.cpid.data): e.form for e in form.items}
    items = [dict(item=transcript_item(cp), cp=cp, form=entries.get(cp.id),
                  notes=cp.vproblem.options.get('grading_notes'), raw=cp.submitted or '')
             for cp in cq.cproblems]
    queue = waiting_for_grading()
    place = next((i for i, w in enumerate(queue) if w.id == cq.id), None)
    return render_template('review.html', cq=cq, form=form, items=items, queue=queue, place=place, came_from=back,
                           others=len([w for w in queue if w.id != cq.id]), title='Grade: {} – {}'.format(cq.taker.shown_name, cq.vquiz.title))


# ---------------------------------------------------------------- students

#route to list users
@qgen_bp.route('/quiz/listuser', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_users():
    """People's Results view (Results by student), in the user folders: ?folder= all (the
    default), main (in no folder) or a folder's id. Its other view is Accounts (user.userdet)."""
    from flask import session
    session['people_view'] = 'results'
    from app import folder_tree
    from app.user import groups
    from .models import RETAKE_RULES
    ulst = User.query.order_by(User.username).all()
    root, flat, nodes, _folders_of = groups.tree(ulst)
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='all')
    shown = node['people'] if node else ulst if view == 'all' else root['people']
    fk = folder_tree.kit(
        view, node, root, flat, nodes, readonly=True,
        page=lambda v: url_for('qgen.list_users', folder=v),
        unit='person', units='people', all_label='All people', all_count=len(ulst), name=lambda f: f.name,
        hint=Markup('Folders are made and filled in <a href="{}">Accounts</a>.').format(url_for('user.userdet', folder=view)),
        fold_key='qgen-folded-results-student-folders')
    return render_template('ulist.html', ulst=ulst, shown=shown, fk=fk, rules=RETAKE_RULES, title='People',
                           folder_heading='Results by person')  # (the owner, 2026-10-16)

#route to list a specific user
@qgen_bp.route('/quiz/listuser/<uid>', methods=['GET'])
@login_required
@pw_check
@admin_only
def list_user(uid):
    ulst = User.query.filter_by(id=uid).first() if str(uid).isdigit() else None
    if ulst is None:
        return gone("That person's account has been deleted.", url_for('user.userdet'))
    from .models import RETAKE_RULES, attempts_by_quiz
    from . import awards
    #their quizzes in the Quizzes page's folders (only the folders with some of theirs in them count)
    quiz_tree = S.subject_tree('quizzes', items=attempts_by_quiz(ulst.cquizzes))[0] if ulst.cquizzes else None
    #the automatic "New" box: quizzes given to them and not started yet
    groups = attempts_by_quiz(ulst.cquizzes)
    fresh = [g for g in groups if any(a.status == 'new' for a in g['attempts'])]
    #and "In progress": started and not handed in yet (like My quizzes' own)
    #(an attempt waiting for grading counts as in progress too)
    working = [g for g in groups if any(a.status in ('started', 'review') for a in g['attempts'])]
    #the folder buttons over their one list of quizzes (static/js/folderfilter.js): New and In
    #progress first, then the Quizzes page's folders that have some of theirs in them
    from app import folder_tree
    def keys(gs):
        return sorted('q:{}'.format(g['vquiz'].id) for g in gs)
    def some(nodes):
        return [dict(n, children=some(n['children'])) for n in nodes if n['count']]
    quiz_filter = [{'id': 'new', 'name': 'New', 'icon': 'sparkle', 'count': len(fresh), 'keys': keys(fresh), 'children': [], 'url': None},
                   {'id': 'started', 'name': 'In progress', 'icon': 'pencil', 'count': len(working), 'keys': keys(working), 'children': [], 'url': None}]
    if quiz_tree:
        quiz_filter += some(folder_tree.filter_tree(quiz_tree, lambda f: f.title, lambda fid: None, 'q:'))
    return render_template('ulist.html', ulst=[ulst], rules=RETAKE_RULES, single=True, title="{}’s student page".format(ulst.shown_name),
                           awards=awards.earned(ulst), quiz_tree=quiz_tree, fresh=fresh, working=working, quiz_filter=quiz_filter)

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
        page=lambda v: url_for('qgen.results_by_quiz', folder=v),
        unit='quiz', units='quizzes', all_label='All quizzes', all_count=len(quizzes), name=lambda f: f.title,
        hint=Markup('The <a href="{}">Quizzes page</a>\'s folders: make and fill them there.').format(url_for('qgen.list_vquizzes')),
        fold_key='qgen-folded-results-quiz-folders')
    return render_template('results_by_quiz.html', quizzes=[results[q.id] for q in shown], results=results, fk=fk,
                           rules=RETAKE_RULES, title='Results by quiz')

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
    #its students in People's folders, like a problem's history (the owner, 2026-10-17)
    from app import folder_tree
    from app.user import groups
    q = quiz_results([vq])[0]
    students = [student for student, _g in q['rows']]
    rows = {student.id: (student, g) for student, g in q['rows']}
    root, flat, nodes, _folders_of = groups.tree(students, only={u.id for u in students})
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='all')
    shown = node['people'] if node else students if view == 'all' else root['people']
    fk = folder_tree.kit(
        view, node, root, flat, nodes, readonly=True,
        page=lambda v: url_for('qgen.quiz_results_page', vqid=vq.id, folder=v),
        unit='student', units='students', all_label='All students', all_count=len(students), name=lambda f: f.name,
        hint=Markup('<a href="{}">People</a>\'s folders: make and fill them there.').format(url_for('user.userdet')),
        fold_key='qgen-folded-quiz-history-folders')
    return render_template('results_by_quiz.html', quizzes=[q], rules=RETAKE_RULES, single=True, fk=fk, shown=shown,
                           rows=rows, title='Quiz history: {}'.format(vq.title))

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
                    'waiting': sum(1 for _, g in rows for cq in g['attempts'] if cq.status == 'review'),
                    'paper': any(get_qtype(p.qtype).paper for p in vq.vproblems)})
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
    return render_template('cqlist.html', cqlst=[cqlst], shown=shown, correct=correct, title="Answer key: {} – {}".format(cqlst.taker.shown_name if cqlst.taker else 'Someone', cqlst.vquiz.title))

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
    flash(Markup('Moved {}\'s attempt at "{}" to the Archive. <a href="{}">View it</a>').format(
        owner, title, url_for('qgen.archived', aid=archived.id)), 'success')
    current_app.logger.info("{} archived {}'s CQuiz: ({}) '{}'".format(current_user.username, owner, cqid, title))
    return redirect(back_to(url_for('qgen.list_users')))

#route to take a quiz away from a student: all their tries at it to the Archive at once
@qgen_bp.route('/quiz/takeaway/<int:vqid>/<int:uid>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def take_away(vqid, uid):
    vq, student = db.session.get(VQuiz, vqid), db.session.get(User, uid)
    if vq is None or student is None:
        return gone('That quiz or student is gone.', back_to(url_for('qgen.list_users')))
    count = S.take_away(student, vq, by=current_user)
    if count:
        flash(Markup('Archived {}’s {} {} at “{}”. {} in the <a href="{}">Archive</a>, where you can view or restore {}.').format(
            student.shown_name, count, 'attempt' if count == 1 else 'attempts', vq.title, 'It’s' if count == 1 else 'They’re',
            url_for('qgen.archive'), 'it' if count == 1 else 'them'), 'success')
        current_app.logger.info("{} took VQuiz ({}) '{}' away from {}: {} archived".format(
            current_user.username, vqid, vq.title, student.username, count))
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
    flash('Assigned a retake of “{}” to {}.'.format(cq.vquiz.title, cq.taker.shown_name), 'success')
    current_app.logger.info('{} assigned retake (of {}) quiz: "{}" ({}) to {}'.format(current_user.username, cqid, cq.vquiz.title, cq.id, cq.taker.username))
    return redirect(back_to(url_for('qgen.list_users')))


# ---------------------------------------------------------------- AI helper

def ai_call(kind, text, work, finish):
    """Every AI button goes through here: session check, API key, size and hourly limits
    (answered at once), then the AI's answer, logged, in the background (app/qgen/ai_jobs.py):
    the page gets {ok, job} and asks /quiz/ai/job/<job> until it's ready. `work(key, text)`
    returns (result, usage); `finish(result)` turns it into (JSON body, status). Tests (TESTING
    without AI_JOBS) get the answer straight away."""
    from datetime import timedelta
    from app import tuning
    from .models import AICall
    from . import ai_jobs
    hourly = tuning.get('ai_hourly')
    if not json_csrf_ok():
        return jsonify(ok=False, error='Your session expired. Please reload the page.'), 400
    key = current_app.config.get('ANTHROPIC_API_KEY')
    if not key:
        return jsonify(ok=False, error='The AI helper isn\'t set up (no API key).'), 400
    text = (text or '').strip()
    if not text:
        return jsonify(ok=False, error='Please describe what you want first.'), 400
    if len(text) > 8000:
        return jsonify(ok=False, error='That\'s too long for the AI helper; please shorten it.'), 400
    since = datetime.now() - timedelta(hours=1)
    if AICall.query.filter(AICall.user_id == current_user.id, AICall.created >= since).count() >= hourly:
        return jsonify(ok=False, error='You\'ve used the AI helper {} times in the last hour. Please wait a bit.'.format(hourly)), 429
    user_id, username = current_user.id, current_user.username

    def run():
        from .ai_helper import AIError
        call = AICall(user_id=user_id, created=datetime.now(), kind=kind, request=text, ok=False)
        try:
            result, usage = work(key, text)
            call.ok = True
            call.input_tokens, call.output_tokens = usage['input_tokens'], usage['output_tokens']
            return finish(result)
        except AIError as exc:
            return {'ok': False, 'error': str(exc)}, 502
        finally:
            db.session.add(call)
            db.session.commit()
            current_app.logger.info('{} used the AI helper ({}, ok={}, tokens in/out {}/{})'.format(
                username, kind, call.ok, call.input_tokens, call.output_tokens))

    if current_app.testing and not current_app.config.get('AI_JOBS'):
        body, status = run()
        return jsonify(body), status
    return jsonify(ok=True, job=ai_jobs.start(user_id, run)), 202

@qgen_bp.route('/quiz/ai/job/<job>', methods=['GET'])
@login_required
@pw_check
@admin_only
def ai_job(job):
    """The page asking whether its AI answer is ready."""
    from . import ai_jobs
    body, status = ai_jobs.collect(job, current_user.id)
    return jsonify(body), status

def ai_fill(kind):
    """Shared by both "Fill in for me" buttons; always answers with JSON."""
    from .ai_helper import ask, problems_with
    body = request.get_json(silent=True) or {}
    text = body.get('text')
    #("Fill in the values": the question already written, for its [names])
    question = str(body.get('question') or '')[:4000] if kind == 'values' else ''

    def finish(fill):
        if fill.get('off_topic'):
            #the helper is for school quiz problems only; nothing else is filled in
            return {'ok': False, 'error': 'The AI helper only writes school quiz problems. Please describe a quiz question for your students.'}, 422
        return {'ok': True, 'fill': fill, 'note': fill.get('cannot_do'), 'problems': problems_with(fill, kind)}, 200
    return ai_call(kind, text, lambda key, t: ask(key, kind, t, question=question), finish)

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

    def finish(result):
        if result['off_topic']:
            return {'ok': False, 'error': 'The AI helper only fills in lists for school quiz problems.'}, 422
        if not result['items']:
            return {'ok': False, 'error': result['cannot_do'] or 'The AI helper couldn\'t make that list. Please describe it another way.'}, 422
        return {'ok': True, 'items': ', '.join(result['items']), 'count': len(result['items']), 'note': result['cannot_do']}, 200
    return ai_call('list', data.get('text'), lambda key, t: ask_list(key, t, columns, context=context), finish)


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
    hints = problem_hints(form.qtype.data, form.question.data, form.answer.data, form.options())
    if not (form.title.data or '').strip():
        #saving needs one too: said here first, so it never comes as a surprise
        from .coach import hint
        hints = [hint('error', 'Give the problem a short title (only you see it), so you can find it in your lists.')] + \
            [h for h in hints if h['level'] != 'ok']
    return jsonify(hints=with_folder_hint('problems', hints, new=not request.args.get('vp', type=int)))

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
    hints = quiz_hints(form.title.data, vpids, form.calculator_ok.data, others, problems,
                       lay=lay, shuffle_order=form.shuffle_order.data)
    return jsonify(hints=with_folder_hint('quizzes', hints, new=not this_id))


# ---------------------------------------------------------------- subjects

#the Problems and Quizzes pages' folders ("subjects" in the code), drawn like every other
#folder list on the site (app/templates/_folders.html); a problem or quiz can be in several

def from_archive():
    """Whether the form was sent from one of the Archive's sections (its folder actions go back there)."""
    from urllib.parse import urlparse
    ref = urlparse(request.referrer or '')
    return ref.path == url_for('qgen.archive') and 'section=' in ref.query


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
    #the same view it was sent from, All included (not the page's remembered one)
    values = {'folder': show} if show.isdigit() or show in ('main', 'all') else {}
    #the same folder tab, when it's the same view (not one the action switched to)
    tab = kept_tab()
    if tab and show == str(request.form.get('view') or 'all'):
        values['tab'] = tab
    if moved and not error:
        values['moved'] = moved
    if from_archive():
        return redirect(url_for('qgen.archive', section=kind, **values))
    return subject_list(kind, **values)

def _item_word(kind, n=1):
    return S.item_word(kind, n)

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
    return _subject_done(kind, 'Folder “{}” made.'.format(subject.title))  # stay where you were

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
    return _subject_done(kind, 'Folder renamed to “{}”.'.format(subject.title))

#route to remove a folder (nothing in it is deleted: it moves up a level)
@qgen_bp.route('/quiz/subjects/<kind>/<int:sid>/delete', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delete_subject(kind, sid):
    from app import takeout
    subject = subject_or_404(kind, sid)
    name, parent = subject.title, subject.parent_id
    said = takeout.folder_delete_plan(kind, subject)  # (what moves where, named in the message)
    S.delete_subject(subject, kind)
    current_app.logger.info('{} deleted {} folder ({}) "{}"'.format(current_user.username, kind, sid, name))
    return _subject_done(kind, said(),
                         show=(parent or 'all') if request.form.get('view') == str(sid) else None)

#route to delete a folder, the folders inside it and what's in them (S.purge_plan: what's
#still needed elsewhere is kept and moves up a level)
@qgen_bp.route('/quiz/subjects/<kind>/<int:sid>/purge', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def purge_subject(kind, sid):
    if kind in S.UPLOAD_KINDS:
        abort(404)  # (uploads are deleted one by one)
    subject = subject_or_404(kind, sid)
    name, parent = subject.title, subject.parent_id
    try:
        plan = S.delete_subject_and_contents(kind, subject)
    except S.ServiceError as exc:
        return _subject_done(kind, 'Not deleted. {}'.format(exc), error=True)
    unit, units = ('problem', 'problems') if kind == 'problems' else ('quiz', 'quizzes')
    def n(count):
        return '{} {}'.format(count, unit if count == 1 else units)
    said = ['Deleted the folder “{}”.'.format(name)]
    if plan['delete']:
        said.append('{} deleted.'.format(n(len(plan['delete']))))
    if plan['remove']:
        said.append('{} removed (students keep their copies).'.format(n(len(plan['remove']))))
    if plan['keep']:
        said.append('{} kept, moved up a level.'.format(n(len(plan['keep']))))
    current_app.logger.info('{} deleted {} folder ({}) "{}" with its contents: {} deleted, {} removed, {} kept'.format(
        current_user.username, kind, sid, name, len(plan['delete']), len(plan['remove']), len(plan['keep'])))
    return _subject_done(kind, ' '.join(said), show=(parent or 'all') if request.form.get('view') == str(sid) else None)

#dragging (and the folder's "Move to" list): a problem or quiz onto a folder (from a folder:
#moved out of that one; from All or Uncategorized: put in it), onto Uncategorized (out
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
    what = S.item_word(kind)
    try:
        if request.form.get('folder'):
            subject = subject_or_404(kind, request.form.get('folder'))
            target = S.get_subject(kind, to) if str(to).isdigit() else None
            S.move_subject(kind, subject, target)
            return _subject_done(kind, 'Moved “{}” to {}.'.format(subject.title, '“{}”'.format(target.title) if target else 'the top'),
                                 moved='folder:{}'.format(subject.id))
        item_id = request.form.get(what)
        if to in (None, '', 'top', 'main'):
            if here is None:
                return _subject_done(kind, 'Drag it out of a folder to take it out.', error=True)
            from app import takeout
            return takeout.handle(kind, [item_id], here.id, lambda m, error=False: _subject_done(kind, m, error=error))
        target = subject_or_404(kind, to)
        item = S.file_one(kind, item_id, target, moving_from=here)
        return _subject_done(kind, ('Moved “{}” to “{}”.' if here else 'Put “{}” in “{}”.').format(item.title, target.title),
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
    what = S.item_word(kind)
    target = subject_or_404(kind, request.form.get('to'))
    try:
        item = S.file_one(kind, request.form.get(what), target)
    except S.ServiceError as exc:
        return _subject_done(kind, str(exc), error=True)
    return _subject_done(kind, 'Put “{}” in “{}”.'.format(item.title, target.title), moved='{}:{}'.format(what, item.id))

@qgen_bp.route('/quiz/subjects/<kind>/remove', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def remove_from_subject(kind):
    #(just that folder; something left in no folder is deleted, asked first: app/takeout.py)
    from app import takeout
    what = S.item_word(kind)
    return takeout.handle(kind, [request.form.get(what)], request.form.get('folder'),
                          lambda m, error=False: _subject_done(kind, m, error=error), one_folder=True)

#route for a "Take out" button on a card or row, and People's checked bar: out of the folder
#shown (and the folders inside it); something left in no folder is deleted, asked first
@qgen_bp.route('/folders/<kind>/takeout', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def take_out_of_folder(kind):
    from app import takeout
    if kind not in takeout.KINDS:
        abort(404)
    if kind == 'people':
        from app.user.routes import _group_done
        done = lambda m, error=False: _group_done(m, error=error)
    elif kind == 'archive':
        done = lambda m, error=False: _archive_done(m, error=error)
    else:
        done = lambda m, error=False: _subject_done(kind, m, error=error)
    items = request.form.getlist('items')
    if not items:
        return done('Check at least one first.', error=True)
    #just=1 (a row's Remove, which asked which folder): only that folder, not the ones inside it
    return takeout.handle(kind, items, request.form.get('folder'), done, one_folder=bool(request.form.get('just')))

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
    #(Take out of folder with no folder open: each out of its own, static/js/filebar.js)
    if not add and request.form.get('subject') == 'own' and items:
        from app import takeout
        return takeout.handle_each(kind, items, lambda m, error=False: _subject_done(kind, m, error=error))
    if subject is None:
        return _subject_done(kind, 'Choose a folder first.', error=True)
    if not items:
        return _subject_done(kind, 'Check at least one first.', error=True)
    if not add:
        #out of the folder chosen; left in no folder: delete it or Uncategorized, asked first
        from app import takeout
        return takeout.handle(kind, items, subject.id, lambda m, error=False: _subject_done(kind, m, error=error), one_folder=True)
    #(one folder or several: the Put in folder dialog lets several be checked, the owner 2026-10-15)
    subjects = [g for g in (S.get_subject(kind, x) for x in dict.fromkeys(request.form.getlist('subject'))) if g is not None]
    #(moving, the dialog's usual way: into one folder, out of the others, the owner 2026-10-16)
    if request.form.get('action') == 'move':
        if len(subjects) != 1:
            return _subject_done(kind, 'Choose one folder to move to.', error=True)
        out_of = S.get_subject(kind, request.form.get('from')) if request.form.get('from') else None
        if out_of is not None:
            #("Move from “X”", from a row's Remove: out of that folder only)
            count = max(S.file_items(kind, items, subjects[0], add=True), S.file_items(kind, items, out_of, add=False))
        else:
            count = S.move_items(kind, items, subjects[0])
        return _subject_done(kind, '{} {} moved to “{}”.'.format(count, _item_word(kind, count), subjects[0].title))
    said = []
    for g in subjects:
        count = S.file_items(kind, items, g, add=add)
        said.append('{} {} put in “{}”.'.format(count, _item_word(kind, count), g.title))
    return _subject_done(kind, ' '.join(said))


def subject_kit(kind, view, node, root, flat, nodes, in_archive=False):
    """The Problems or Quizzes page's folders, for _folders.html (in_archive: the Archive's
    Problems or Quizzes, the same page for the ones moved to the Archive)."""
    from app import folder_tree
    page = LIST_PAGES[kind]
    unit, units = S.ITEM_WORDS[kind]
    upload = kind in S.UPLOAD_KINDS
    #(example folder names that suit the things: the owner, 2026-10-19)
    first, second = {'pictures': ('Animals', 'Maps'), 'files': ('Worksheets', 'Answer keys')}.get(kind, ('Algebra', 'Period 2'))
    examples = '“{}” or “{}”'.format(first, second)
    return folder_tree.kit(
        view, node, root, flat, nodes,
        page=(lambda v: url_for('qgen.archive', section=kind, folder=v)) if in_archive else (lambda v: url_for(page, folder=v)),
        create_url=url_for('qgen.new_subject', kind=kind), move_url=url_for('qgen.move_subject', kind=kind),
        rename_url=lambda fid: url_for('qgen.rename_subject', kind=kind, sid=fid),
        delete_url=lambda fid: url_for('qgen.delete_subject', kind=kind, sid=fid),
        add_url=url_for('qgen.add_to_subject', kind=kind), remove_url=url_for('qgen.remove_from_subject', kind=kind),
        unit=unit, units=units, all_label='All ' + units, all_count=root['all_count'],
        name=lambda f: f.title, placeholder='e.g. ' + first, add_words='+', drag_what='a ' + unit,
        hint='Your own folders for sorting {}, e.g. {}. A {} can be in several folders. '
             'Students never see them.'.format(units, examples, unit),
        fold_key='qgen-folded-{}-folders'.format(kind),
        #(no "Delete folder and everything in it" for uploads: deleting files is done one by one)
        purge_url=None if upload else (lambda fid: url_for('qgen.purge_subject', kind=kind, sid=fid)),
        purge_question=None if upload else (lambda n: S.purge_question(kind, n['folder'])))


def subject_page(kind, template, in_archive=False, **extra):
    """The Problems or Quizzes page: ?folder= all (the default), main (uncategorized) or a
    folder's id. in_archive: the Archive's Problems or Quizzes (the ones moved there), the same
    page with Restore and Delete for good on each (the owner, 2026-10-16)."""
    from app import folder_tree
    _g, item_cls, rel, _b = S.subject_kind(kind)
    if in_archive:
        everything = item_cls.query.filter(item_cls.removed_at.isnot(None)).order_by(item_cls.id.desc()).all()
        root, flat, nodes = S.subject_tree(kind, items=everything)
    else:
        root, flat, nodes = S.subject_tree(kind)
        everything = S.in_use(kind).order_by(*(S.upload_order(kind) if kind in S.UPLOAD_KINDS else (item_cls.id.desc(),))).all()
    root['all_count'] = len(everything)
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='all')
    shown = node['items'] if node else everything if view == 'all' else root['items']
    fk = subject_kit(kind, view, node, root, flat, nodes, in_archive=in_archive)
    #(speed, the owner 2026-10-20: every row's folders in one query, not one query a row; and for
    #problems, which have any answers at all (History) in one query, not each one's every answer)
    if everything and kind not in S.UPLOAD_KINDS:
        from sqlalchemy.orm import selectinload
        ids = [x.id for x in everything]
        item_cls.query.options(selectinload(getattr(item_cls, rel))).filter(item_cls.id.in_(ids)).all()
    if kind == 'problems':
        from .models import CProblem
        extra.setdefault('answered', {pid for (pid,) in db.session.query(CProblem.vproblem_id).distinct()})
    return render_template(template, fk=fk, items=shown, total=len(everything), kind=kind, in_archive=in_archive,
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
    #their own (a teacher who took it too): told as a student is
    if a.student_id == current_user.id:
        flash('Your teacher has taken this quiz away.', 'info')
        return redirect(url_for('user.mypage'))
    if current_user.is_admin:
        return redirect(url_for('qgen.archived', aid=a.id))
    abort(404)

def archive_kit(view, node, root, flat, nodes, total):
    """The Archive's folders, for _folders.html."""
    from app import folder_tree
    return folder_tree.kit(
        view, node, root, flat, nodes,
        page=lambda v: url_for('qgen.archive', folder=v),
        create_url=url_for('qgen.new_archive_folder'), move_url=url_for('qgen.move_archive_item'),
        rename_url=lambda fid: url_for('qgen.rename_archive_folder', fid=fid),
        delete_url=lambda fid: url_for('qgen.delete_archive_folder', fid=fid),
        unit='attempt', units='attempts', all_label='All attempts', all_count=total,
        name=lambda f: f.name, folder_icon=lambda f: 'user' if f.student_id else 'folder',
        placeholder='e.g. 2025-26', add_words='Move to…', drag_what='an attempt',
        hint='Each student has a folder (the one with a person on it) for his/her archived attempts; you can add your own and put folders inside folders.',
        fold_key='qgen-folded-archive-folders',
        purge_url=lambda fid: url_for('qgen.purge_archive_folder', fid=fid),
        purge_question=lambda n: archive_purge_question(n['folder']))


def archive_purge_question(folder):
    count, inner = S.archive_folder_count(folder), len(S.archive_subtree(folder)) - 1
    return 'Delete the folder “{}”{} and the {} archived attempt{} in it for good? This can’t be undone: {} can’t be ' \
           'viewed or restored afterwards.'.format(
               folder.name, ' and the {} folder{} inside it'.format(inner, '' if inner == 1 else 's') if inner else '',
               count, '' if count == 1 else 's', 'it' if count == 1 else 'they') if count else \
        'Delete the folder “{}”{}? It’s empty.'.format(folder.name, ' and the folders inside it' if inner else '')

def _archive_done(message, error=False, show=None, moved=None):
    """After a change to the Archive's folders: JSON for the page's script (a drag), else back
    to the Archive showing the same folder (or `show`)."""
    if request.headers.get('X-Requested-With') == 'fetch':
        return (jsonify(ok=False, error=message), 400) if error else jsonify(ok=True, message=message)
    flash(message, 'error' if error else 'success')
    show = str(request.form.get('view') or 'all') if show is None else str(show)
    values = {'folder': show} if show.isdigit() or show in ('main', 'all') else {}
    #the same folder tab, when it's the same view (not one the action switched to)
    tab = kept_tab()
    if tab and show == str(request.form.get('view') or 'all'):
        values['tab'] = tab
    if moved and not error:
        values['moved'] = moved
    return redirect(url_for('qgen.archive', **values))

#route to the archive of deleted attempts: ?folder= all (the default), main (uncategorized)
#or a folder's id
@qgen_bp.route('/quiz/archive', methods=['GET'])
@login_required
@pw_check
@admin_only
def archive():
    #the sections over the Archive (the owner, 2026-10-16): Attempts (the folders below), and
    #the quizzes, problems and people moved to the Archive by their trash cans
    section = request.args.get('section', 'attempts')
    counts = archive_counts()
    if section == 'quizzes':
        return subject_page('quizzes', 'vqlist.html', in_archive=True, title='Archive', section=section, counts=counts,
                            layout=layout, rules=RETAKE_RULES, all_subjects=S.subject_tree('quizzes')[1],
                            archived=S.archived_counts()[0], archive_warning=S.archive_warning, removed_count=counts['quizzes'])
    if section == 'problems':
        return subject_page('problems', 'vplist.html', in_archive=True, title='Archive', section=section, counts=counts,
                            qtypes=REGISTRY, all_subjects=S.subject_tree('problems')[1], quizzes=[],
                            archived=S.archived_counts()[1], archive_warning=S.archive_warning,
                            blockers={p.id: S.problem_delete_blocker(p) for p in S.removed_problems()})
    if section == 'people':
        from app.user.routes import people_page
        return people_page(in_archive=True, section=section, counts=counts)
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
                           section='attempts', counts=counts,
                           moved=request.args.get('moved', ''))

def archive_counts():
    """How many are in each of the Archive's sections."""
    from app.qgen.models import ArchivedAttempt
    from app.user.accounts import archived_people
    return {'attempts': ArchivedAttempt.query.count(), 'quizzes': len(S.removed_quizzes()),
            'problems': len(S.removed_problems()), 'people': len(archived_people())}


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
    return _archive_done('Folder “{}” made.'.format(folder.name))  # stay where you were

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
    return _archive_done('Folder renamed to “{}”.'.format(folder.name))

#route to remove an Archive folder (what's in it moves up a level)
@qgen_bp.route('/quiz/archive/folders/<int:fid>/delete', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delete_archive_folder(fid):
    from app import takeout
    from app.qgen.models import ArchiveFolder, ArchivedAttempt
    folder = archive_folder_or_404(fid)
    name, parent = folder.name, folder.parent_id
    #(what moves where, for the message: the attempts and folders in it go up a level)
    up = db.session.get(ArchiveFolder, parent).name if parent else None
    tries = sorted('{}’s “{}”'.format(a.student_name, a.quiz_title) for a in ArchivedAttempt.query.filter_by(folder_id=fid))
    inner = sorted(g.name for g in ArchiveFolder.query.filter_by(parent_id=fid, removed=False))
    S.delete_archive_folder(folder)
    current_app.logger.info('{} deleted archive folder ({}) "{}"'.format(current_user.username, fid, name))
    return _archive_done(takeout.moved_up_message(name, up, tries, inner),
                         show=(parent or 'all') if request.form.get('view') == str(fid) else None)

#route to delete an Archive folder with the folders and archived attempts in it, for good
@qgen_bp.route('/quiz/archive/folders/<int:fid>/purge', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def purge_archive_folder(fid):
    folder = archive_folder_or_404(fid)
    name, parent = folder.name, folder.parent_id
    gone = S.delete_archive_folder_and_contents(folder)
    current_app.logger.info('{} deleted archive folder ({}) "{}" and {} archived attempts'.format(current_user.username, fid, name, gone))
    return _archive_done('Deleted the folder “{}”{}.'.format(name, ' and its {} archived attempt{}'.format(gone, '' if gone == 1 else 's') if gone else ''),
                         show=(parent or 'all') if request.form.get('view') == str(fid) else None)

#dragging, and the "Move to…" lists: an archived attempt onto a folder (or Uncategorized),
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
    where = '“{}”'.format(target.name) if target else S.UNSORTED
    try:
        if request.form.get('folder'):
            folder = archive_folder_or_404(request.form.get('folder'))
            S.move_archive_folder(folder, target)
            return _archive_done('Moved “{}” to {}.'.format(folder.name, '“{}”'.format(target.name) if target else 'the top'),
                                 moved='folder:{}'.format(folder.id))
        a = db.session.get(ArchivedAttempt, int(request.form.get('attempt'))) if str(request.form.get('attempt', '')).isdigit() else None
        if a is None:
            return _archive_done('That archived attempt isn\'t there any more.', error=True)
        S.move_archived([a.id], target)
        return _archive_done('Moved {}\'s “{}” to {}.'.format(a.student_name, a.quiz_title, where), moved='attempt:{}'.format(a.id))
    except S.ServiceError as exc:
        return _archive_done(str(exc), error=True)

#route to move the checked archived attempts to a folder (or to Uncategorized)
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
                                                             '“{}”'.format(folder.name) if folder else S.UNSORTED))

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
    flash('Restored {}\'s attempt at “{}”; {} can see it again.'.format(name, title, name), 'success')
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
    flash('Deleted {}\'s attempt at “{}” for good.'.format(name, title), 'success')
    current_app.logger.info('{} purged archived CQuiz ({}) of {} "{}"'.format(current_user.username, original, name, title))
    return redirect(back_to_list('qgen.archive'))


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
    from .scan_routes import scan_progress_data
    return render_template('dashboard.html', title='Dashboard', refresh_ms=tuning.dashboard_ms(), scans=scan_progress_data(current_user),
                           **dashboard_data())

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
