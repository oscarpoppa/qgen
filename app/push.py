"""Instant updates: the server tells open pages "something changed" the moment it's saved.

Every open page keeps a connection to the server (Socket.IO, static/js/push.js). Whenever a
change is saved to the database, the pages it could affect are told at once, and each one
runs its usual check-in straight away (static/js/messages.js; app/live.py says whether the
page itself has changed) and the Dashboard redraws. Nothing about the change itself is
sent: only "check now", so a page never learns anything its own check-in wouldn't tell it.

Who is told:
- a change to someone's own things (their attempts, answers, messages, folders...): that
  person and the teachers
- a change everyone may see (a quiz or problem edited, a setting, a teacher's name): everyone
- someone coming online, signing out or opening/leaving a quiz page: the teachers
- autosaved answers don't tell the person typing them (their own quiz page leaves them
  out anyway)

While connected, a page also says "still here" over the connection every check-in time
(Technical settings), which keeps people "online" and announces quizzes that have
opened; the full check-in then runs only every few minutes, as a backup. Without a
connection (it dropped, or push is off) pages check in every check-in time as before.

Push is off unless the server is started with QGEN_PUSH=1. It needs a server that keeps
many connections open at once: one gunicorn worker with threads
(gunicorn --workers 1 --threads 100 ...), and nginx passing /socket.io on as WebSockets.
With several worker processes it must stay off.
"""
from datetime import datetime
from urllib.parse import urlsplit

from flask import current_app, has_request_context, request
from flask_login import current_user
from flask_socketio import SocketIO, disconnect, join_room
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

socketio = SocketIO()

TEACHERS = 'teachers'
EVERYONE = '*'

#saved by the site for its own bookkeeping; no page shows them
QUIET_TABLES = {'ai_call', 'scan_job', 'api_token', 'login_failure'}
#a person's columns written by check-ins: only coming online or a change of quiz page matters
SEEN_COLUMNS = {'last_seen', 'logged_in', 'on_quiz', 'on_quiz_at'}


def enabled():
    return bool(current_app.config.get('PUSH'))


def _same_site(origin, environ):
    """A connection may only come from a page on this site. Behind nginx the Host has no
    port ("localhost" for "localhost:8080"): then the same name on any port counts."""
    if not origin:
        return False
    parts = urlsplit(origin)
    host = environ.get('HTTP_HOST', '')
    if parts.netloc == host:
        return True
    if host.startswith('['):
        name, _, rest = host[1:].partition(']')
        port = rest[1:]
    else:
        name, _, port = host.partition(':')
    return not port and parts.hostname is not None and parts.hostname == name.lower()


def init(app):
    app.config.setdefault('PUSH', False)
    socketio.init_app(app, async_mode='threading', cors_allowed_origins=_same_site,
                      manage_session=False, logger=False, engineio_logger=False)


# ---------------------------------------------------------------- who to tell

def _user_rooms(user_id):
    return {'user:{}'.format(user_id), TEACHERS} if user_id else {TEACHERS}


def _person(obj, state, whole):
    """Rooms for a change to a person's own row (whole: added or deleted)."""
    if whole:
        return {EVERYONE} if obj.is_admin else {TEACHERS}
    changed = {a.key for a in state.attrs if a.history.has_changes()}
    if not changed:
        return set()
    if changed <= SEEN_COLUMNS:
        out = set()
        hist = state.attrs.last_seen.history
        before = hist.deleted[0] if hist.deleted else obj.last_seen
        from app import tuning
        if 'logged_in' in changed or 'on_quiz' in changed or before is None \
                or datetime.now() - before >= tuning.online_window():
            out.add(TEACHERS)  # came online, signed out, opened or left a quiz page
        return out
    #a teacher's name or picture shows on students' pages too
    return {EVERYONE} if obj.is_admin else _user_rooms(obj.id)


def _rooms_for(session, obj, whole=False):
    """whole: the row was added or deleted (in after_flush the session still lists
    what the flush did, and each row's history still holds its changes)."""
    table = getattr(obj, '__tablename__', None)
    if table in QUIET_TABLES:
        return set()
    state = inspect(obj)
    if table == 'user':
        return _person(obj, state, whole)
    if not whole and not session.is_modified(obj, include_collections=False):
        return set()
    if table == 'cproblem':
        from app.qgen.models import CQuiz
        from sqlalchemy.orm.util import identity_key
        #its attempt, if it's loaded (it always is when answers are saved or graded)
        cq = session.identity_map.get(identity_key(CQuiz, obj.cquiz_id)) if obj.cquiz_id else None
        return _user_rooms(cq.assignee) if cq is not None else {TEACHERS}
    if table == 'staff_message' or table.startswith('staff_message_'):
        return {TEACHERS}
    for column in ('assignee', 'student_id', 'user_id', 'owner_id'):
        if hasattr(obj, column):
            return _user_rooms(getattr(obj, column))
    return {EVERYONE}


@event.listens_for(Session, 'after_flush')
def _collect(session, flush_context):
    rooms = session.info.setdefault('push_rooms', set())
    for obj in session.new:
        rooms |= _rooms_for(session, obj, whole=True)
    for obj in session.dirty:
        rooms |= _rooms_for(session, obj)
    for obj in session.deleted:
        rooms |= _rooms_for(session, obj, whole=True)


@event.listens_for(Session, 'after_commit')
def _send(session):
    rooms = session.info.pop('push_rooms', None)
    if rooms:
        tell(rooms)


@event.listens_for(Session, 'after_rollback')
def _forget(session):
    session.info.pop('push_rooms', None)


def not_me():
    """What this request saves isn't news to the person making it (autosaved answers)."""
    if current_user.is_authenticated:
        request.environ['qgen.push_not_me'] = current_user.id


def tell(rooms):
    """Send "check now" to these rooms (EVERYONE: every connected page)."""
    try:
        if not enabled():
            return
    except RuntimeError:  # no app (a script)
        return
    rooms = set(rooms)
    if has_request_context() and request.environ.get('qgen.push_not_me'):
        #noted beforehand: right after a commit the database can't be asked who's signed in
        rooms.discard('user:{}'.format(request.environ['qgen.push_not_me']))
    try:
        if EVERYONE in rooms:
            socketio.emit('changed', {})
            return
        if rooms:
            socketio.emit('changed', {}, to=sorted(rooms))
    except Exception as exc:  # never let it break a save
        current_app.logger.error('push failed: {}'.format(exc))


def sign_out(user_id):
    """Close this person's connections (they reconnect at once where they're still signed in)."""
    if not enabled():
        return
    try:
        room = 'user:{}'.format(user_id)
        for sid, _ in list(socketio.server.manager.get_participants('/', room)):
            socketio.server.disconnect(sid, namespace='/')
    except Exception as exc:
        current_app.logger.error('push sign-out failed: {}'.format(exc))


# ---------------------------------------------------------------- the connection

@socketio.on('connect')
def _connect(auth=None):
    if not enabled() or not current_user.is_authenticated:
        return False
    join_room('user:{}'.format(current_user.id))
    if current_user.is_admin:
        join_room(TEACHERS)


@socketio.on('here')
def _here(data=None):
    """A connected page, every check-in time: still here, on this page."""
    if not current_user.is_authenticated:
        disconnect()
        return
    from app.user.models import note_seen, note_page
    user = current_user._get_current_object()
    note_seen(user)
    watch = data.get('watch') if isinstance(data, dict) else None
    note_page(user, watch if isinstance(watch, str) else None)
    from app.qgen.services import announce_opened
    from app import db
    try:
        announce_opened(student_id=user.id)
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error('announcing opened quizzes failed: {}'.format(exc))
