"""Pages that keep themselves up to date.

A page says what it shows with <body data-watch="students" data-watch-state="...">
(see watch() below). Every page already checks in every so often (messages.js and
/messages/poll); the check-in sends the page's watch key and gets back a short
fingerprint of what that page shows right now. When the fingerprint differs from the
one the page was drawn with, the page reloads itself, or, when someone is typing on
it, offers a Refresh button instead.

A fingerprint covers what the page displays and nothing else, so a page only reloads
when something on it would change: an attempt assigned, started, handed in, graded,
retaken or deleted, a rule changed, a quiz opening, a new student...
Keys a person may not see give None (the page then never reloads).
"""
import hashlib
from datetime import datetime, timedelta

from flask import request
from flask_login import current_user
from markupsafe import Markup, escape

from app import db


def _digest(rows):
    return hashlib.sha1(repr(rows).encode()).hexdigest()[:16]


def _attempt_row(cq, now):
    """What lists of attempts show about one: where it is, its score and its rules."""
    return (cq.id, cq.assignee, cq.vquiz_id, cq.status, cq.not_open_yet(now), cq.score,
            cq.retake_rule, cq.opens_at, cq.closes_at, cq.time_limit)


def _quiz_row(vq):
    return (vq.id, vq.title, vq.retake_rule)


def _attempts(query, now, opening=True):
    """The rows for a list of attempts, read as plain columns (not the answers, and the
    quizzes in one go), so a poll stays quick however many attempts there are. opening:
    whether the page shows "opens at..." (the teachers' results pages don't)."""
    from app.qgen.models import CQuiz, VQuiz
    rows = query.with_entities(CQuiz.id, CQuiz.assignee, CQuiz.vquiz_id, CQuiz.completed, CQuiz.needs_review,
                               CQuiz.startdate, CQuiz.opens_at, CQuiz.score, CQuiz.retake_rule,
                               CQuiz.closes_at, CQuiz.time_limit).order_by(CQuiz.id).all()
    out = []
    for r in rows:
        status = 'completed' if r.completed else 'review' if r.needs_review else 'started' if r.startdate else 'new'
        not_open = bool(opening and r.opens_at and now < r.opens_at)
        out.append((r.id, r.assignee, r.vquiz_id, status, not_open, r.score, r.retake_rule,
                    r.opens_at, r.closes_at, r.time_limit))
    ids = sorted({r.vquiz_id for r in rows if r.vquiz_id is not None})
    quizzes = VQuiz.query.filter(VQuiz.id.in_(ids)).with_entities(VQuiz.id, VQuiz.title, VQuiz.retake_rule) \
        .order_by(VQuiz.id).all() if ids else []
    return out, [tuple(q) for q in quizzes]


# ---------------------------------------------------------------- one per kind of page

def _mine(now):
    """Someone's My quizzes, and how they've arranged it in folders (another tab of theirs follows)."""
    from app.qgen.models import CQuiz, QuizFolder, QuizPlacement
    folders = [(f.id, f.parent_id, f.name) for f in QuizFolder.query.filter_by(owner_id=current_user.id).order_by(QuizFolder.id)]
    placed = sorted((p.vquiz_id, p.folder_id) for p in QuizPlacement.query.filter_by(owner_id=current_user.id))
    return _attempts(CQuiz.query.filter_by(assignee=current_user.id), now), folders, placed


def _home(now):
    """A student's Home: their quizzes (not how they're arranged in folders), and which are
    "due soon" and "recently completed" now, so the page moves on as time passes."""
    from app import tuning
    from app.qgen.models import CQuiz
    from app.user.routes import RECENT_DAYS
    rows, quizzes = _attempts(CQuiz.query.filter_by(assignee=current_user.id), now)
    q = CQuiz.query.filter_by(assignee=current_user.id)
    soon = [r[0] for r in q.filter(CQuiz.completed.is_(False), CQuiz.needs_review.is_(False),
                                   CQuiz.closes_at >= now, CQuiz.closes_at <= now + tuning.due_soon())
            .with_entities(CQuiz.id).order_by(CQuiz.id)]
    recent = [r[0] for r in q.filter(db.or_(CQuiz.completed.is_(True), CQuiz.needs_review.is_(True)),
                                     CQuiz.compdate >= now - timedelta(days=RECENT_DAYS))
              .with_entities(CQuiz.id).order_by(CQuiz.id)]
    return rows, quizzes, soon, recent


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
        return (_attempt_row(cq, now), cq.startdate, cq.compdate,
                [(cp.id, cp.submitted, cp.credit, cp.feedback) for cp in cq.cproblems])
    if cq.assignee != current_user.id:
        return None
    return (cq.completed, cq.needs_review, cq.not_open_yet(now), cq.score,
            cq.opens_at, cq.closes_at, cq.time_limit)


def _students(uid, now):
    """Results by student (everyone, or one student)."""
    from app.qgen.models import CQuiz
    from app.user.models import User
    users = User.query.order_by(User.id)
    attempts = CQuiz.query
    if uid is not None:
        users, attempts = users.filter(User.id == uid), attempts.filter(CQuiz.assignee == uid)
        if users.first() is None:
            return 'gone'
    return [(u.id, u.username, u.nickname, u.is_admin, u.avatar) for u in users], _attempts(attempts, now, opening=False)


def _review(now):
    """The Grading list: who, which quiz, and how many answers are still without a grade
    (a draft saved by another teacher changes that)."""
    from app.qgen.models import CQuiz, CProblem, VQuiz
    from app.user.models import User
    rows = db.session.query(CQuiz.id, CQuiz.compdate, User.username, User.nickname, VQuiz.title) \
        .join(User, User.id == CQuiz.assignee).join(VQuiz, VQuiz.id == CQuiz.vquiz_id) \
        .filter(CQuiz.needs_review.is_(True), CQuiz.completed.is_(False)).order_by(CQuiz.id).all()
    ids = [r[0] for r in rows]
    todo = dict(db.session.query(CProblem.cquiz_id, db.func.count(CProblem.id))
                .filter(CProblem.cquiz_id.in_(ids), CProblem.credit.is_(None))
                .group_by(CProblem.cquiz_id).all()) if ids else {}
    return [tuple(r) + (todo.get(r[0], 0),) for r in rows]


def _quiz_folders():
    """Which quiz is in which of the Quizzes page's folders, and the folders' names."""
    from app.qgen.models import VQGroup, vquiz_vqgroup
    return ([(g.id, g.title) for g in VQGroup.query.order_by(VQGroup.id)],
            sorted(tuple(r) for r in db.session.query(vquiz_vqgroup.c.vquiz_id, vquiz_vqgroup.c.vqgroup_id)))


def _quizzes(vqid, now):
    """The quiz list (or one quiz): titles, rules, how often each is assigned and how
    many students have their own rule, and the archive count."""
    from app.qgen.models import CQuiz, VQuiz, ArchivedAttempt
    quizzes = VQuiz.query.order_by(VQuiz.id)
    if vqid is not None:
        quizzes = quizzes.filter(VQuiz.id == vqid)
    counts = dict(db.session.query(CQuiz.vquiz_id, db.func.count(CQuiz.id)).group_by(CQuiz.vquiz_id).all())
    #students with a rule of their own that really differs from the quiz's
    own = dict(db.session.query(CQuiz.vquiz_id, db.func.count(db.distinct(CQuiz.assignee)))
               .join(VQuiz, VQuiz.id == CQuiz.vquiz_id)
               .filter(CQuiz.retake_rule.isnot(None), CQuiz.retake_rule != VQuiz.retake_rule)
               .group_by(CQuiz.vquiz_id).all())
    quizzes = quizzes.with_entities(VQuiz.id, VQuiz.title, VQuiz.retake_rule, VQuiz.vpid_lst, VQuiz.calculator_ok,
                                    VQuiz.shuffle_order, VQuiz.image).all()
    if vqid is not None and not quizzes:
        return 'gone'
    return ([tuple(vq) + (counts.get(vq.id, 0), own.get(vq.id, 0)) for vq in quizzes],
            ArchivedAttempt.query.count(), _quiz_folders(), _problem_rows())


def _problem_rows():
    """What lists of problems show about each (its question, type, picture, calculator)."""
    from app.qgen.models import VProblem
    return [tuple(r) for r in VProblem.query.with_entities(VProblem.id, VProblem.title, VProblem.raw_prob, VProblem.raw_ansr,
                                                             VProblem.qtype, VProblem.image, VProblem.calculator_ok).order_by(VProblem.id)]


def _problems(now):
    """The Problems page: the problems, and which of its folders each is in."""
    from app.qgen.models import VPGroup, vproblem_vpgroup
    return (_problem_rows(), [(g.id, g.title) for g in VPGroup.query.order_by(VPGroup.id)],
            sorted(tuple(r) for r in db.session.query(vproblem_vpgroup.c.vproblem_id, vproblem_vpgroup.c.vpgroup_id)))


def _byquiz(vqid, now):
    """Results by quiz (every quiz, attempts or not), or one quiz's results (only its own
    attempts: other quizzes' hand-ins don't reload it)."""
    from app.qgen.models import CQuiz, VQuiz
    from app.user.models import User
    quizzes = VQuiz.query.order_by(VQuiz.id)
    attempts = CQuiz.query
    if vqid is not None:
        quizzes, attempts = quizzes.filter(VQuiz.id == vqid), attempts.filter(CQuiz.vquiz_id == vqid)
    rows = quizzes.with_entities(VQuiz.id, VQuiz.title, VQuiz.retake_rule).all()
    if vqid is not None and not rows:
        return 'gone'
    return ([tuple(r) for r in rows], [tuple(u) for u in User.query.with_entities(User.id, User.username, User.nickname, User.avatar).order_by(User.id)],
            _attempts(attempts, now, opening=False), _quiz_folders())


def _archive(aid, now):
    """The Archive (or one archived attempt): what's in which folder, the folders, the
    students' names (their folders are named after them) and whether each attempt can
    still be put back (its student and quiz still there)."""
    from app.qgen.models import ArchivedAttempt, ArchiveFolder, VQuiz
    from app.user.models import User
    users = {u.id: u.username for u in User.query.with_entities(User.id, User.username)}
    quizzes = {r[0] for r in VQuiz.query.with_entities(VQuiz.id)}
    def row(a):
        return (a.id, a.folder_id, a.student_id in users, a.vquiz_id in quizzes)
    cols = (ArchivedAttempt.id, ArchivedAttempt.folder_id, ArchivedAttempt.student_id, ArchivedAttempt.vquiz_id)
    if aid is not None:
        a = ArchivedAttempt.query.filter_by(id=aid).with_entities(*cols).first()
        return 'gone' if a is None else row(a)
    return ([row(a) for a in ArchivedAttempt.query.with_entities(*cols).order_by(ArchivedAttempt.id)],
            [(f.id, f.name, f.student_id) for f in ArchiveFolder.query.filter_by(removed=False).order_by(ArchiveFolder.id)],
            sorted(users.items()))


def _users(now):
    """The Users page: who's there, and when each was last seen."""
    from app.user.models import User
    def seen(u):
        #"just now", "N min ago" and "N h ago" move on all day: counted as one, so the page
        #doesn't reload every few minutes while anyone is about (it still does for someone
        #coming online or going, and for the day changing)
        label = u.seen_label(now)
        return 'today' if label == 'just now' or label.endswith(' min ago') or label.endswith(' h ago') else label
    from app.user import groups
    return [(u.id, u.username, u.nickname, u.email, u.is_admin, u.avatar, seen(u)) for u in User.query.order_by(User.id)], groups.state()


def _students_named():
    from app.user.models import User
    return [tuple(u) for u in User.query.filter_by(is_admin=False).with_entities(User.id, User.username, User.nickname, User.avatar).order_by(User.id)]


def _messages(now):
    """The Messages page: what the teacher's messages show, the unread count, the students
    (names and pictures) and the Users page's folders (shown there too)."""
    from app.messages.routes import messages_state
    from app.messages.models import unread_messages_for_teacher
    from app.user import groups
    return messages_state(), unread_messages_for_teacher(current_user.id), _students_named(), groups.state()


def _conversation(student_id, now):
    """One conversation (opening it marks it read): that student's messages, their name and
    picture, and how many are unread altogether (shown in the switch-student list).
    Messages with other students don't reload it otherwise."""
    from app.messages.models import Message, NOT_NOTICE, for_teacher, unread_messages_for_teacher
    from app.user.models import User
    student = db.session.get(User, student_id)
    if student is None:
        return 'gone'
    thread = Message.query.filter(Message.student_id == student_id, NOT_NOTICE, for_teacher(current_user.id)) \
        .with_entities(db.func.count(Message.id), db.func.max(Message.id),
                       db.func.sum(db.case((Message.pinned.is_(True), Message.id), else_=0)),
                       db.func.sum(db.case((Message.hidden_for_student.is_(True), Message.id), else_=0))).one()
    return tuple(thread), unread_messages_for_teacher(current_user.id), _students_named()


def _assign(now):
    """The Assign page: the quizzes to choose from (and their folders), the people and the
    Users page's folders."""
    from app.qgen.models import VQuiz
    from app.user import groups
    from app.user.models import User
    return ([tuple(q) for q in VQuiz.query.with_entities(VQuiz.id, VQuiz.title).order_by(VQuiz.id)], _quiz_folders(),
            [tuple(u) for u in User.query.with_entities(User.id, User.username, User.nickname, User.is_admin).order_by(User.id)], groups.state())


def _grading(cqid, now):
    """The grading page of one attempt: its answers and the grades saved so far (another
    teacher's draft, or the attempt being archived)."""
    from app.qgen.models import CQuiz, CProblem
    cq = db.session.get(CQuiz, cqid)
    if cq is None:
        return 'gone'
    return (cq.completed, cq.needs_review,
            [tuple(r) for r in CProblem.query.filter_by(cquiz_id=cqid)
             .with_entities(CProblem.id, CProblem.submitted, CProblem.credit, CProblem.feedback).order_by(CProblem.id)])


def _editquiz(vqid, now):
    """A quiz being edited: the quiz itself, and the students with a rule of their own."""
    from app.qgen.models import CQuiz, VQuiz
    vq = VQuiz.query.filter_by(id=vqid).with_entities(VQuiz.id, VQuiz.title, VQuiz.retake_rule, VQuiz.vpid_lst,
                                                      VQuiz.calculator_ok, VQuiz.shuffle_order, VQuiz.image).first()
    if vq is None:
        return 'gone'
    own = sorted(tuple(r) for r in CQuiz.query.filter(CQuiz.vquiz_id == vqid, CQuiz.retake_rule.isnot(None))
                 .with_entities(CQuiz.assignee, CQuiz.retake_rule))
    return tuple(vq), own, _quiz_folders()


# key -> (teachers only?, function(argument, now))
KINDS = {
    'mine': (False, lambda arg, now: _mine(now)),  # a teacher's own quizzes too
    'home': (False, lambda arg, now: _home(now)),
    'attempt': (False, _attempt),
    'students': (True, lambda arg, now: _students(None, now)),
    'student': (True, _students),
    'byquiz': (True, lambda arg, now: _byquiz(None, now)),
    'quizresults': (True, _byquiz),
    'review': (True, lambda arg, now: _review(now)),
    'grading': (True, _grading),
    'quizzes': (True, lambda arg, now: _quizzes(None, now)),
    'quiz': (True, _quizzes),
    'editquiz': (True, _editquiz),
    'problems': (True, lambda arg, now: _problems(now)),
    'assign': (True, lambda arg, now: _assign(now)),
    'archive': (True, lambda arg, now: _archive(None, now)),
    'archived': (True, _archive),
    'users': (True, lambda arg, now: _users(now)),
    'messages': (True, lambda arg, now: _messages(now)),
    'conversation': (True, _conversation),
}

WITH_ID = {'attempt', 'student', 'quizresults', 'grading', 'quiz', 'editquiz', 'archived', 'conversation'}


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
    if request.method == 'POST':
        out += ' data-watch-post'
    return Markup(out)
