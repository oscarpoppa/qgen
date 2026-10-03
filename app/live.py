"""Pages that keep themselves up to date.

A page says what it shows with <body data-watch="students" data-watch-state="...">
(see watch() below). Every page already checks in every so often (messages.js and
/messages/poll); the check-in sends the page's watch key and gets back a short
fingerprint of what that page shows right now. When the fingerprint differs from the
one the page was drawn with, the page reloads itself, or, when someone is typing on
it, offers a Refresh button instead.

A fingerprint covers what the page displays and nothing else, so a page only reloads
when something on it would change: an attempt assigned, started, handed in, graded,
retaken or deleted, answers released, a rule changed, a quiz opening, a new student...
Keys a person may not see give None (the page then never reloads).
"""
import hashlib
from datetime import datetime

from flask_login import current_user
from markupsafe import Markup, escape

from app import db


def _digest(rows):
    return hashlib.sha1(repr(rows).encode()).hexdigest()[:16]


def _attempt_row(cq, now):
    """What lists of attempts show about one: where it is, its score and its rules."""
    return (cq.id, cq.assignee, cq.vquiz_id, cq.status, cq.not_open_yet(now), cq.score,
            cq.retake_rule, bool(cq.answers_released), cq.opens_at, cq.closes_at, cq.time_limit)


def _quiz_row(vq):
    return (vq.id, vq.title, vq.retake_rule, bool(vq.hide_answers), bool(vq.answers_released))


def _attempts(query, now):
    from app.qgen.models import CQuiz
    rows = query.order_by(CQuiz.id).all()
    quizzes = {cq.vquiz_id: cq.vquiz for cq in rows}
    return [_attempt_row(cq, now) for cq in rows], [_quiz_row(quizzes[k]) for k in sorted(quizzes)]


# ---------------------------------------------------------------- one per kind of page

def _mine(now):
    """A student's My quizzes."""
    from app.qgen.models import CQuiz
    return _attempts(CQuiz.query.filter_by(assignee=current_user.id), now)


def _attempt(cqid, now):
    """One attempt: the quiz page, its results, "being graded", "opens at ...", or a
    teacher's Details page. The taker's own page leaves out what they do themselves
    (starting, saving answers), so typing never reloads it; their page's timer hands
    it in when time is up. A teacher's view also follows the answers as they're saved."""
    from app.qgen.models import CQuiz
    from app.qgen.routes import archived_for
    cq = db.session.get(CQuiz, cqid)
    if cq is None:
        return 'archived' if archived_for(cqid) else 'gone'
    #a teacher taking a quiz themselves is its taker here: their own saving isn't news
    if current_user.is_admin and cq.assignee != current_user.id:
        return (_attempt_row(cq, now), cq.startdate, cq.compdate, cq.answers_visible,
                [(cp.id, cp.submitted, cp.credit, cp.feedback) for cp in cq.cproblems])
    if cq.assignee != current_user.id:
        return None
    return (cq.completed, cq.needs_review, cq.not_open_yet(now), cq.score, cq.answers_visible,
            cq.opens_at, cq.closes_at, cq.time_limit)


def _students(uid, now):
    """Results by student (everyone, or one student)."""
    from app.qgen.models import CQuiz
    from app.user.models import User
    users = User.query.order_by(User.id)
    attempts = CQuiz.query
    if uid is not None:
        users, attempts = users.filter(User.id == uid), attempts.filter(CQuiz.assignee == uid)
    return [(u.id, u.username, u.is_admin, u.avatar) for u in users], _attempts(attempts, now)


def _review(now):
    from app.qgen.models import CQuiz
    return [(cq.id, cq.assignee, cq.vquiz_id) for cq in
            CQuiz.query.filter_by(needs_review=True, completed=False).order_by(CQuiz.id)]


def _quizzes(vqid, now):
    """The quiz list (or one quiz): titles, rules, how often each is assigned and how
    many students have their own rule, and the archive count."""
    from app.qgen.models import CQuiz, VQuiz, ArchivedAttempt
    quizzes = VQuiz.query.order_by(VQuiz.id)
    if vqid is not None:
        quizzes = quizzes.filter(VQuiz.id == vqid)
    counts = dict(db.session.query(CQuiz.vquiz_id, db.func.count(CQuiz.id)).group_by(CQuiz.vquiz_id).all())
    own = dict(db.session.query(CQuiz.vquiz_id, db.func.count(db.distinct(CQuiz.assignee)))
               .filter(CQuiz.retake_rule.isnot(None)).group_by(CQuiz.vquiz_id).all())
    return ([_quiz_row(vq) + (counts.get(vq.id, 0), own.get(vq.id, 0)) for vq in quizzes],
            ArchivedAttempt.query.count())


def _archive(aid, now):
    from app.qgen.models import ArchivedAttempt, ArchiveFolder
    if aid is not None:
        a = db.session.get(ArchivedAttempt, aid)
        return 'gone' if a is None else (a.id, a.folder_id)
    return ([(a.id, a.folder_id) for a in ArchivedAttempt.query.order_by(ArchivedAttempt.id)],
            [(f.id, f.name) for f in ArchiveFolder.query.order_by(ArchiveFolder.id)])


def _users(now):
    """The Users page: who's there, and when each was last seen."""
    from app.user.models import User
    def seen(u):
        #"just now" / "N min ago" move on every minute: counted as one, so the page
        #doesn't reload each minute while anyone is about (it still does for online,
        #and for the hour or day changing)
        label = u.seen_label(now)
        return 'minutes' if label == 'just now' or label.endswith(' min ago') else label
    return [(u.id, u.username, u.email, u.is_admin, u.avatar, seen(u)) for u in User.query.order_by(User.id)]


def _messages(student_id, now):
    """The Messages page or one conversation (which marks what it shows as read)."""
    from app.messages.routes import messages_state
    from app.messages.models import unread_for_teachers
    return messages_state(), unread_for_teachers(current_user.id)


# key -> (teachers only?, function(argument, now))
KINDS = {
    'mine': (False, lambda arg, now: _mine(now)),  # a teacher's own quizzes too
    'attempt': (False, _attempt),
    'students': (True, lambda arg, now: _students(None, now)),
    'student': (True, _students),
    'review': (True, lambda arg, now: _review(now)),
    'quizzes': (True, lambda arg, now: _quizzes(None, now)),
    'quiz': (True, _quizzes),
    'archive': (True, lambda arg, now: _archive(None, now)),
    'archived': (True, _archive),
    'users': (True, lambda arg, now: _users(now)),
    'messages': (True, lambda arg, now: _messages(None, now)),
    'conversation': (True, _messages),
}

WITH_ID = {'attempt', 'student', 'quiz', 'archived', 'conversation'}


def state(key, now=None):
    """The fingerprint of what the page named by key shows, or None if there's no such
    page or this person can't see it."""
    if not key or not current_user.is_authenticated:
        return None
    kind, _, arg = str(key).partition(':')
    if kind not in KINDS:
        return None
    admin_only, fn = KINDS[kind]
    if admin_only and not current_user.is_admin:
        return None
    #a kind for one thing takes its number; the others take nothing
    if (kind in WITH_ID) != bool(arg) or (arg and not arg.isdigit()):
        return None
    arg = int(arg) if arg else None
    rows = fn(arg, now or datetime.now())
    return None if rows is None else _digest(rows)


def watch(key, note=None, button=None, ask=False):
    """The <body> attributes that make a page keep itself up to date. note/button word
    the offer to refresh; ask=True always offers instead of reloading by itself."""
    current = state(key)
    if current is None:
        return Markup('')
    out = ' data-watch="{}" data-watch-state="{}"'.format(escape(key), current)
    if note:
        out += ' data-watch-note="{}"'.format(escape(note))
    if button:
        out += ' data-watch-button="{}"'.format(escape(button))
    if ask:
        out += ' data-watch-ask'
    return Markup(out)
