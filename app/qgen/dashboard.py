"""The administrators' Dashboard: what needs doing and what's going on. Its time
spans and list lengths are Technical settings (app/tuning.py).

Everything here only reads. In particular, looking at students' messages here doesn't
mark them read (that happens in Messages, as before).
"""
from datetime import timedelta

from flask import current_app
from sqlalchemy.orm import joinedload

from app import db, tuning
from app.messages.models import unread_messages_for_teacher, unread_notices_for_teachers
from app.user.models import User
from .models import CQuiz, VQuiz, VProblem, ArchivedAttempt, AICall, Setting
from .services import attempt_state



def _students():
    return User.query.filter(User.is_admin.isnot(True))


def _waiting():
    return CQuiz.query.filter(CQuiz.needs_review.is_(True), CQuiz.completed.is_(False))


def _unfinished():
    return CQuiz.query.filter(CQuiz.completed.is_(False), CQuiz.needs_review.is_(False))


def closing_soon(now):
    """Unfinished attempts that close within the "due soon" days, soonest first."""
    return (_unfinished().filter(CQuiz.closes_at >= now, CQuiz.closes_at <= now + tuning.due_soon())
            .options(joinedload(CQuiz.taker), joinedload(CQuiz.vquiz)).order_by(CQuiz.closes_at).all())


def counts(teacher, now):
    """The to-do numbers at the top."""
    return {'grading': _waiting().count(),
            'messages': unread_messages_for_teacher(teacher.id),  # from students and from other teachers
            'notices': unread_notices_for_teachers(teacher.id),
            'closing': len(closing_soon(now))}


def online(now):
    """Everyone active in the last couple of minutes, by name."""
    return User.query.filter(User.online_condition(now)).order_by(User.username).all()




def recently_active(now):
    """People seen in the last hour who aren't online now, most recent first."""
    return (User.query.filter(User.last_seen >= now - tuning.recently(), ~User.online_condition(now))
            .order_by(User.last_seen.desc()).all())


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


def out_now(now, limit=None):
    """Assigned attempts not handed in yet (not started, or started), newest assignment
    first: ([{'cq', 'state': 'new' | 'started' | 'not_open'}], how many in all)."""
    q = _unfinished()
    limit = limit or tuning.get('list_assigned')
    rows = (q.options(joinedload(CQuiz.taker), joinedload(CQuiz.vquiz))
            .order_by(CQuiz.create_date.desc(), CQuiz.id.desc()).limit(limit).all())
    out = []
    for cq in rows:
        state = 'not_open' if cq.not_open_yet(now) else 'started' if cq.startdate else 'new'
        out.append({'cq': cq, 'state': state})
    return out, q.count()


def grading_queue(limit=None):
    """The attempts waiting longest for grading (the same order as Grading), and how many wait."""
    q = _waiting()
    limit = limit or tuning.get('list_grading')
    return (q.options(joinedload(CQuiz.taker), joinedload(CQuiz.vquiz)).order_by(CQuiz.compdate, CQuiz.id).limit(limit).all(),
            q.count())


def recent_handins(limit=None):
    """The latest attempts handed in (graded, or waiting for grading), newest first."""
    limit = limit or tuning.get('list_handins')
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


def site_glance(now):
    """Counts and settings at a glance."""
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    calls = db.session.query(db.func.count(AICall.id),
                             db.func.coalesce(db.func.sum(AICall.input_tokens), 0),
                             db.func.coalesce(db.func.sum(AICall.output_tokens), 0)).filter(AICall.created >= month).one()
    return {'students': _students().count(),
            'teachers': User.query.filter(User.is_admin.is_(True)).count(),
            'problems': VProblem.query.count(),
            'quizzes': VQuiz.query.filter(VQuiz.removed_at.is_(None)).count(),
            'archived': ArchivedAttempt.query.count(),
            'signup_open': bool(Setting.get('class_code')),
            'ai_on': bool(current_app.config.get('ANTHROPIC_API_KEY')),
            'ai_calls': calls[0], 'ai_tokens': int(calls[1]) + int(calls[2]),
            'month': '{:%B}'.format(now)}


def pinned():
    """The pinned messages, newest first: one entry per message sent together, with the
    students it's pinned for and how many of them have read it."""
    from app.messages.models import Message
    groups = {}
    for m in Message.query.filter(Message.pinned.is_(True)).options(joinedload(Message.student)) \
            .order_by(Message.created.desc(), Message.id.desc()):
        g = groups.setdefault(m.batch or m.id, {'msg': m, 'to': [], 'read': 0})
        if m.student is not None:
            g['to'].append(m.student)
        g['read'] += 1 if m.seen_by_student else 0
    out = list(groups.values())
    for g in out:
        g['to'].sort(key=lambda u: u.username.lower())
        g['everyone'] = len(g['to']) > 1 and len(g['to']) == _students().count()
    return out
