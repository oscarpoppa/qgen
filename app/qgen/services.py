"""What teachers and students can do with quizzes, independent of how they ask.

The web pages (routes.py) and the REST API (app/api) both call these
functions, so grading, randomizing and the rules around them can never
drift apart. Nothing here reads the request, flashes messages or renders
pages; problems are reported by raising ServiceError (worded for people)
or by returning lists of plain-language errors.
"""
import json
import random
from datetime import datetime, timedelta

from flask import url_for

from app import db
from app.messages.models import notify
from . import layout
from .formfact import record_answers, finalize
from .friendly import FriendlyError
from .models import CQuiz, VQuiz, VProblem, CProblem, VPGroup, VQGroup, RETAKE_RULES
from .qtypes import get_qtype

#answers are still accepted this long after the deadline (slow connections, the auto-submit)
GRACE = timedelta(minutes=2)


class ServiceError(ValueError):
    """Something the person asked for can't be done, worded for them."""


def archive(obj, group_cls, rel):
    group = group_cls.query.filter_by(title='Archive').first()
    if group:
        getattr(obj, rel).append(group)


# ---------------------------------------------------------------- problems

def problem_errors(qtype, question, answer, options):
    """Plain-language errors; empty when the problem is ready to save."""
    return get_qtype(qtype).validate(question, answer, options)


def save_problem(vp, qtype, title, question, answer, options, calculator_ok=False):
    """Check and save a problem (new or existing). Returns errors; saves only if there are none."""
    errors = problem_errors(qtype, question, answer, options)
    if not (title or '').strip():
        errors = ['Please give the problem a short title.'] + errors
    if errors:
        return errors
    new = vp.id is None
    if new:
        db.session.add(vp)
    vp.qtype, vp.title, vp.raw_prob, vp.raw_ansr = qtype, title.strip(), question, answer
    vp.options = options
    #first picture kept in the old column for older pages and quizzes
    images = options.get('images') or []
    vp.image = images[0]['file'] if images else None
    vp.calculator_ok = bool(calculator_ok)
    if new:
        archive(vp, VPGroup, 'vpgroups')
    vp.save()
    return []


def problem_delete_blocker(vp):
    """Why a problem can't be deleted, or None if it can."""
    if vp.vquizzes:
        return 'Problem "{}" is used by these quizzes: {}.'.format(
            vp.title, ', '.join('"{}"'.format(q.title) for q in vp.vquizzes))
    if vp.cproblems:
        #students' answers to it are part of their records
        return ('Problem "{}" has {} student answer{} on record. You can take it out of quizzes instead; '
                'it just won\'t be used again.'.format(vp.title, len(vp.cproblems), '' if len(vp.cproblems) == 1 else 's'))
    return None


def delete_problem(vp):
    blocker = problem_delete_blocker(vp)
    if blocker:
        raise ServiceError(blocker)
    db.session.delete(vp)
    db.session.commit()


def instantiate_problem(vprob, rng=random):
    """One student's own random version of a problem: (text, answer, extra data)."""
    qt = get_qtype(vprob.qtype)
    #problems are checked before saving, but if a rare draw still can't be
    #worked out (e.g. an edge case in an old problem), draw again
    for attempt in range(50):
        try:
            return qt.instantiate(vprob.raw_prob, vprob.raw_ansr, vprob.options, rng)
        except FriendlyError:
            if attempt == 49:
                raise ServiceError('Problem "{}" couldn\'t be set up; please open it and check it.'.format(vprob.title))


def preview_problem(qtype, question, answer, options, count=3):
    """A few sample versions, without saving; (errors, samples)."""
    errors = problem_errors(qtype, question, answer, options)
    if errors:
        return errors, []
    qt, rng, samples = get_qtype(qtype), random.Random(), []
    for _ in range(count):
        prob, ansr, co = qt.instantiate(question, answer, options, rng)
        samples.append({'text': prob, 'correct': qt.show_correct(ansr, co), 'choices': co.get('choices'),
                        'right': co.get('correct', []), 'image': co.get('image')})
    return [], samples


# ---------------------------------------------------------------- quizzes

QUIZ_SETTINGS = ('image', 'calculator_ok', 'shuffle_order', 'retake_rule', 'hide_answers')


def check_layout(value):
    """A quiz's problem list (text, JSON or already parsed) -> (layout, errors)."""
    try:
        lay = layout.parse(value) if isinstance(value, str) else layout.parse(json.dumps(value or []))
    except (layout.LayoutError, TypeError, ValueError) as exc:
        return [], [str(exc) if isinstance(exc, layout.LayoutError) else 'The list of problems couldn\'t be read.']
    if not lay:
        return lay, ['Choose at least one problem.']
    missing = [n for n in set(layout.all_ids(lay)) if not db.session.get(VProblem, n)]
    if missing:
        return lay, ['These problems no longer exist: {}'.format(', '.join(map(str, sorted(missing))))]
    return lay, layout.check(lay)


def save_vquiz(vq, title, problems, author_id=None, **settings):
    """Check and save a quiz (new or existing). Returns errors; saves only if there are none."""
    lay, errors = check_layout(problems)
    if not (title or '').strip():
        errors = ['Please give the quiz a title.'] + errors
    if settings.get('retake_rule') and settings['retake_rule'] not in RETAKE_RULES:
        errors.append('Unknown retake rule "{}".'.format(settings['retake_rule']))
    if errors:
        return errors
    new = vq.id is None
    if new:
        vq.author_id = author_id
        #in the session before links are made, so lookups below don't trip over it
        db.session.add(vq)
    vq.title = title.strip()
    for key in QUIZ_SETTINGS:
        if key in settings:
            if key == 'hide_answers' and vq.hide_answers != settings[key]:
                vq.answers_released = False
            setattr(vq, key, settings[key])
    vq.vpid_lst = layout.dumps(lay)
    vq.vproblems = [db.session.get(VProblem, a) for a in set(layout.all_ids(lay))]
    if new:
        archive(vq, VQGroup, 'vqgroups')
    vq.save()
    return []


def vquiz_delete_blocker(vq):
    if vq.cquizzes:
        return 'Quiz "{}" has been assigned {} time{}. Delete those assignments first.'.format(
            vq.title, len(vq.cquizzes), '' if len(vq.cquizzes) == 1 else 's')
    return None


def delete_vquiz(vq):
    blocker = vquiz_delete_blocker(vq)
    if blocker:
        raise ServiceError(blocker)
    db.session.delete(vq)
    db.session.commit()


def release_answers(vq, released):
    """Show (or hide again) correct answers on results pages; tells students when shown."""
    vq.answers_released = bool(released)
    if vq.answers_released:
        for cq in {c.assignee: c for c in vq.cquizzes if c.completed}.values():
            notify(cq.assignee, 'The correct answers for "{}" are now on your results page.'.format(vq.title),
                   url_for('qgen.qtake', cidx=cq.id))
    vq.save()


# ---------------------------------------------------------------- assigning

def create_cquiz(vquiz, assignee, opens_at=None, closes_at=None, time_limit=None):
    """One student's own copy of a quiz. Raises ServiceError if it can't be made."""
    try:
        cq = CQuiz(vquiz_id=vquiz.id, assignee=assignee.id, opens_at=opens_at, closes_at=closes_at, time_limit=time_limit)
        #groups ("2 of these 6") are drawn separately for each student
        ordered = layout.draw(layout.parse(vquiz.vpid_lst), random)
        #so "question 1 is B" means nothing to the student next door
        if vquiz.shuffle_order:
            random.shuffle(ordered)
        for ordinal, pid in enumerate(ordered, 1):
            vprob = db.session.get(VProblem, pid)
            prob, ansr, opts = instantiate_problem(vprob)
            cp = CProblem(ordinal=ordinal, conc_prob=prob, conc_ansr=ansr, vproblem_id=vprob.id)
            cp.conc_opts = opts
            cq.cproblems.append(cp)
        cq.save()
        return cq
    except ServiceError:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        raise ServiceError('Couldn\'t create "{}" for {}: {}'.format(vquiz.title, assignee.username, exc))


def assign(vquiz, students, opens_at=None, closes_at=None, time_limit=None):
    """Give each student their own copy; returns (created quizzes, [(student, error), ...])."""
    if opens_at and closes_at and closes_at <= opens_at:
        raise ServiceError('The closing time must be after the opening time.')
    if time_limit is not None and not 1 <= time_limit <= 600:
        raise ServiceError('The time limit must be between 1 and 600 minutes.')
    created, failed = [], []
    for student in students:
        try:
            cq = create_cquiz(vquiz, student, opens_at, closes_at, time_limit)
        except ServiceError as exc:
            failed.append((student, str(exc)))
            continue
        when = ' It opens {}.'.format(cq.opens_at.strftime('%b %d at %I:%M %p')) if cq.opens_at else ''
        notify(student.id, 'New quiz: "{}".{}'.format(vquiz.title, when), url_for('qgen.qtake', cidx=cq.id))
        created.append(cq)
    db.session.commit()
    return created, failed


def retake(cq):
    """A fresh copy, with new values, of a quiz the student has taken."""
    if not (cq.completed or cq.needs_review):
        raise ServiceError('{} hasn\'t finished "{}" yet.'.format(cq.taker.username, cq.vquiz.title))
    new = create_cquiz(cq.vquiz, cq.taker)
    new.retake_rule = cq.retake_rule
    notify(cq.assignee, 'You can try "{}" again.'.format(cq.vquiz.title), url_for('qgen.qtake', cidx=new.id))
    db.session.commit()
    return new


def delete_attempt(cq):
    CProblem.query.filter_by(cquiz_id=cq.id).delete()
    db.session.delete(cq)
    db.session.commit()


def set_retake_rule(cq, rule):
    """How this student's attempts at this quiz combine; None = the quiz's own rule."""
    if rule and rule not in RETAKE_RULES:
        raise ServiceError('Unknown retake rule "{}".'.format(rule))
    #kept on every attempt so it survives deleting one
    for other in CQuiz.query.filter_by(assignee=cq.assignee, vquiz_id=cq.vquiz_id):
        other.retake_rule = rule or None
    db.session.commit()


# ---------------------------------------------------------------- taking

def attempt_state(cq, now=None):
    """'completed', 'review' (waiting for a teacher), 'not_open', 'time_up' or 'open'."""
    now = now or datetime.now()
    if cq.completed:
        return 'completed'
    if cq.needs_review:
        return 'review'
    if cq.not_open_yet(now):
        return 'not_open'
    deadline = cq.deadline()
    if deadline and now > deadline + GRACE:
        return 'time_up'
    return 'open'


def close_expired(now=None):
    """Hand in and score every attempt whose time is up, even if the student never
    comes back. Returns how many were closed. Called by the app about once a
    minute (see app/__init__.py) and by `flask close-expired`."""
    now = now or datetime.now()
    candidates = CQuiz.query.filter(CQuiz.completed.is_(False), CQuiz.needs_review.is_(False),
                                    db.or_(CQuiz.closes_at.isnot(None),
                                           db.and_(CQuiz.time_limit.isnot(None), CQuiz.startdate.isnot(None)))).all()
    closed = 0
    for cq in candidates:
        if attempt_state(cq, now) == 'time_up':
            submit(cq)
            closed += 1
    return closed


def start(cq):
    """The student opened the quiz: the time limit starts now."""
    if not cq.startdate:
        cq.startdate = datetime.now()
        cq.save()


def _answers_by_ordinal(cq, answers):
    """Only answers to this quiz's questions; keys may be ints or strings."""
    by_ordinal = {cp.ordinal: cp for cp in cq.cproblems}
    out = {}
    for key, value in (answers or {}).items():
        try:
            ordinal = int(key)
        except (TypeError, ValueError):
            raise ServiceError('"{}" isn\'t a question number.'.format(key))
        if ordinal not in by_ordinal:
            raise ServiceError('This quiz has no question {}.'.format(ordinal))
        out[ordinal] = value
    return out


def autosave(cq, answers):
    """Save answers so far without handing in. answers: {question number: answer}."""
    state = attempt_state(cq)
    if state in ('completed', 'review'):
        raise ServiceError('This quiz has already been submitted.')
    if state == 'not_open':
        raise ServiceError('This quiz isn\'t open yet.')
    if state == 'time_up':
        raise ServiceError('Time is up.')
    start(cq)
    for ordinal, value in _answers_by_ordinal(cq, answers).items():
        cp = next(c for c in cq.cproblems if c.ordinal == ordinal)
        cp.submitted = get_qtype(cp.vproblem.qtype).to_stored(value)
    db.session.commit()


def submit(cq, answers=None):
    """Hand in: grade what can be graded now. With answers=None (time ran out),
    the autosaved answers are used. Returns 'completed' or 'review'."""
    if attempt_state(cq) in ('completed', 'review'):
        raise ServiceError('This quiz has already been submitted.')
    if attempt_state(cq) == 'not_open':
        raise ServiceError('This quiz isn\'t open yet.')
    if answers is not None:
        answers = _answers_by_ordinal(cq, answers)
    if record_answers(cq, answers):
        cq.needs_review = True
        cq.save()
        return 'review'
    finalize(cq)
    cq.save()
    return 'completed'


# ---------------------------------------------------------------- grading

def essays(cq):
    return [cp for cp in cq.cproblems if not get_qtype(cp.vproblem.qtype).auto_graded]


def grade_essays(cq, grades, finish=False, grader_id=None):
    """grades: {cproblem id: {'credit': 0-100 or None, 'feedback': str, 'highlights': [[start, end, 'right'|'wrong'], ...]}}.
    Saves them; with finish=True also closes the quiz and tells the student.
    Returns the question numbers still needing a credit (nothing is finished then)."""
    if cq.completed:
        raise ServiceError('That quiz has already been graded.')
    if not cq.needs_review:
        raise ServiceError('That quiz hasn\'t been submitted yet.')
    by_id = {cp.id: cp for cp in essays(cq)}
    for cpid, g in (grades or {}).items():
        cp = by_id.get(int(cpid))
        if not cp:
            raise ServiceError('Answer {} isn\'t a written answer in this quiz.'.format(cpid))
        if 'credit' in g:
            credit = g['credit']
            if credit is not None and not 0 <= float(credit) <= 100:
                raise ServiceError('Credit must be between 0 and 100.')
            cp.credit = None if credit is None else float(credit) / 100.0
        if 'feedback' in g:
            cp.feedback = (g['feedback'] or '').strip() or None
        if 'highlights' in g:
            spans = []
            for s in g['highlights'] or []:
                try:
                    if s[2] in ('right', 'wrong'):
                        spans.append([int(s[0]), int(s[1]), s[2]])
                except (TypeError, ValueError, IndexError):
                    continue
            cp.highlights = spans
    if not finish:
        db.session.commit()
        return []
    ungraded = [cp.ordinal for cp in by_id.values() if cp.credit is None]
    if ungraded:
        db.session.commit()
        return sorted(ungraded)
    cq.graded_by = grader_id
    cq.graded_date = datetime.now()
    finalize(cq)
    notify(cq.assignee, 'Your written answers in "{}" have been graded: {:.0f}%.'.format(cq.vquiz.title, cq.score),
           url_for('qgen.qtake', cidx=cq.id))
    cq.save()
    return []
