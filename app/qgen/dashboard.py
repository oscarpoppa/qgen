"""The administrators' Dashboard: what needs doing and what's going on.

Everything here only reads. In particular, looking at students' messages here doesn't
mark them read (that happens in Messages, as before).
"""
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy.orm import joinedload, selectinload

from app import db
from app.messages.models import Message, NOT_NOTICE, seen_by, unread_for_teachers, unread_notices_for_teachers
from app.user.models import User, ONLINE_WINDOW
from .models import CQuiz, VQuiz, VProblem, ArchivedAttempt, AICall, Setting, attempts_by_quiz
from .services import attempt_state

#"closing soon": an unfinished attempt that closes within this long
SOON = timedelta(days=2)
#quizzes (and missed attempts) still worth showing after they're done
RECENT = timedelta(days=14)
#a student whose counted scores average below this is listed to check on
LOW_AVERAGE = 50


def _students():
    return User.query.filter(User.is_admin.isnot(True))


def _waiting():
    return CQuiz.query.filter(CQuiz.needs_review.is_(True), CQuiz.completed.is_(False))


def _unfinished():
    return CQuiz.query.filter(CQuiz.completed.is_(False), CQuiz.needs_review.is_(False))


def closing_soon(now):
    """Unfinished attempts that close within SOON, soonest first."""
    return (_unfinished().filter(CQuiz.closes_at >= now, CQuiz.closes_at <= now + SOON)
            .options(joinedload(CQuiz.taker), joinedload(CQuiz.vquiz)).order_by(CQuiz.closes_at).all())


def counts(teacher, now):
    """The to-do numbers at the top."""
    return {'grading': _waiting().count(),
            'messages': unread_for_teachers(teacher.id),
            'notices': unread_notices_for_teachers(teacher.id),
            'closing': len(closing_soon(now))}


def online(now):
    """Everyone active in the last couple of minutes, by name."""
    return User.query.filter(User.last_seen >= now - ONLINE_WINDOW).order_by(User.username).all()


def taking_now(now):
    """Students online with a started attempt they can still answer:
    [{'cq', 'started', 'left' (timedelta, or None without a limit or close time)}]."""
    here = [u.id for u in online(now) if not u.is_admin]
    if not here:
        return []
    rows = (_unfinished().filter(CQuiz.assignee.in_(here), CQuiz.startdate.isnot(None))
            .options(joinedload(CQuiz.taker), joinedload(CQuiz.vquiz)).order_by(CQuiz.startdate).all())
    out = []
    for cq in rows:
        if attempt_state(cq, now) != 'open':
            continue
        deadline = cq.deadline()
        out.append({'cq': cq, 'started': cq.startdate, 'left': max(deadline - now, timedelta(0)) if deadline else None})
    return out


def grading_queue(limit=5):
    """The attempts waiting longest for grading (the same order as Review), and how many wait."""
    q = _waiting()
    return (q.options(joinedload(CQuiz.taker), joinedload(CQuiz.vquiz)).order_by(CQuiz.compdate, CQuiz.id).limit(limit).all(),
            q.count())


def recent_handins(limit=10):
    """The latest attempts handed in (graded, or waiting for grading), newest first."""
    return (CQuiz.query.filter(db.or_(CQuiz.completed.is_(True), CQuiz.needs_review.is_(True)), CQuiz.compdate.isnot(None))
            .options(joinedload(CQuiz.taker), joinedload(CQuiz.vquiz))
            .order_by(CQuiz.compdate.desc(), CQuiz.id.desc()).limit(limit).all())


def when(d, now):
    """'Today 3:05 PM', 'Tomorrow 9:00 AM', 'Fri 3:00 PM' within a week, else 'Oct 9'."""
    clock = '{}:{:%M} {:%p}'.format(d.hour % 12 or 12, d, d)
    days = (d.date() - now.date()).days
    if days == 0:
        return 'today ' + clock
    if days == 1:
        return 'tomorrow ' + clock
    if days == -1:
        return 'yesterday ' + clock
    if -6 <= days <= 6:
        return '{:%a} {}'.format(d, clock)
    return '{:%b} {}'.format(d, d.day)


def students_to_check(now):
    """Students who may need a word: [{'student', 'reasons': [text]}], by name.
    - hasn't started a quiz that closes within SOON
    - let a quiz close (in the last RECENT) without starting it
    - counted scores (by each quiz's retake rule, as on My quizzes) average under LOW_AVERAGE"""
    out = []
    for student in _students().options(selectinload(User.cquizzes)).order_by(User.username).all():
        reasons = []
        for cq in sorted(student.cquizzes, key=lambda c: c.closes_at or now):
            if cq.startdate or not cq.closes_at or cq.needs_review:
                continue
            if not cq.completed and now <= cq.closes_at <= now + SOON:
                reasons.append('Hasn\'t started “{}” (closes {})'.format(cq.vquiz.title, when(cq.closes_at, now)))
            elif now - RECENT <= cq.closes_at < now:
                reasons.append('Missed “{}” (closed {})'.format(cq.vquiz.title, when(cq.closes_at, now)))
        scores = [g['combined'] for g in attempts_by_quiz(student.cquizzes) if g['combined'] is not None]
        if scores and sum(scores) / len(scores) < LOW_AVERAGE:
            reasons.append('Average score {:.0f}% over {} quiz{}'.format(
                sum(scores) / len(scores), len(scores), '' if len(scores) == 1 else 'zes'))
        if reasons:
            out.append({'student': student, 'reasons': reasons})
    return out


def quiz_progress(now):
    """Quizzes out now (an attempt not handed in) or handed in lately:
    [{'vquiz', 'assigned', 'finished', 'waiting', 'average', 'closes'}], soonest closing first."""
    recent = db.or_(db.and_(CQuiz.completed.is_(False), CQuiz.needs_review.is_(False)),
                    CQuiz.needs_review.is_(True), CQuiz.compdate >= now - RECENT)
    ids = {r[0] for r in db.session.query(CQuiz.vquiz_id).filter(recent).distinct()}
    if not ids:
        return []
    attempts = CQuiz.query.filter(CQuiz.vquiz_id.in_(ids)).options(joinedload(CQuiz.vquiz)).order_by(CQuiz.id).all()
    by_quiz = {}
    for cq in attempts:
        by_quiz.setdefault(cq.vquiz_id, []).append(cq)
    out = []
    for vqid, rows in by_quiz.items():
        students = {}
        for cq in rows:
            students.setdefault(cq.assignee, []).append(cq)
        scores = [g['combined'] for s in students.values() for g in attempts_by_quiz(s) if g['combined'] is not None]
        closes = [cq.closes_at for cq in rows if not cq.completed and not cq.needs_review and cq.closes_at and cq.closes_at >= now]
        out.append({'vquiz': rows[0].vquiz, 'assigned': len(students),
                    'finished': sum(1 for s in students.values() if any(c.completed for c in s)),
                    'waiting': sum(1 for c in rows if c.needs_review and not c.completed),
                    'average': sum(scores) / len(scores) if scores else None,
                    'closes': min(closes) if closes else None})
    far = now + timedelta(days=36500)
    return sorted(out, key=lambda r: (r['closes'] or far, (r['vquiz'].title or '').lower()))


def recent_messages(teacher, limit=5):
    """The newest messages from students: [(message, unread for this teacher)]. Marks nothing."""
    rows = (Message.query.filter(Message.from_teacher.is_(False), NOT_NOTICE)
            .options(joinedload(Message.student)).order_by(Message.created.desc(), Message.id.desc()).limit(limit).all())
    unread = {r[0] for r in db.session.query(Message.id).filter(Message.id.in_([m.id for m in rows] or [0]),
                                                                ~seen_by(teacher.id))}
    return [(m, m.id in unread) for m in rows]


def site_glance(now):
    """Counts and settings at a glance."""
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    calls = db.session.query(db.func.count(AICall.id),
                             db.func.coalesce(db.func.sum(AICall.input_tokens), 0),
                             db.func.coalesce(db.func.sum(AICall.output_tokens), 0)).filter(AICall.created >= month).one()
    return {'students': _students().count(),
            'teachers': User.query.filter(User.is_admin.is_(True)).count(),
            'problems': VProblem.query.count(),
            'quizzes': VQuiz.query.count(),
            'archived': ArchivedAttempt.query.count(),
            'signup_open': bool(Setting.get('class_code')),
            'ai_on': bool(current_app.config.get('ANTHROPIC_API_KEY')),
            'ai_calls': calls[0], 'ai_tokens': int(calls[1]) + int(calls[2]),
            'month': '{:%B}'.format(now)}
