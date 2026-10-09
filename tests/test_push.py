"""Instant updates (app/push.py): who is told "something changed", and when."""
import pytest

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_archive import ids
from test_dashboard import make_quiz


@pytest.fixture
def push_on(app_db):
    app, db = app_db
    app.config['PUSH'] = True
    yield app, db
    app.config['PUSH'] = False


def fresh():
    """The tests share one app context, where Flask-Login keeps the last person it loaded;
    a real connection gets its own (see fresh_login_per_request in conftest.py)."""
    from flask import g
    g.pop('_login_user', None)


def connect(app, client):
    from app.push import socketio
    fresh()
    return socketio.test_client(app, flask_test_client=client)


def here(sock, watch='mine'):
    fresh()
    sock.emit('here', {'watch': watch})


def told(sock):
    """Whether this page was told "something changed" since last asked (and forget it)."""
    return any(m['name'] == 'changed' for m in sock.get_received())


def test_off_unless_the_server_is_started_for_it(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    assert not connect(app, teacher).is_connected()
    page = teacher.get('/dashboard').data.decode()
    assert 'push.js' not in page and 'socket.io' not in page
    # with it off, saving tells no one and doesn't fail
    make_quiz(app, teacher)


def test_only_signed_in_pages_on_this_site_connect(push_on):
    app, db = push_on
    assert not connect(app, app.test_client()).is_connected()
    teacher = login(app, 'teach')
    assert connect(app, teacher).is_connected()
    page = teacher.get('/dashboard').data.decode()
    assert 'socket.io/4.7.5/socket.io.min.js' in page and 'js/push.js' in page
    from app.push import _same_site
    assert _same_site('http://localhost:8080', {'HTTP_HOST': 'localhost:8080'})
    assert _same_site('http://localhost:8080', {'HTTP_HOST': 'localhost'})  # behind nginx
    assert not _same_site('http://evil.example', {'HTTP_HOST': 'localhost'})
    assert not _same_site('http://evil.example:8080', {'HTTP_HOST': 'localhost:8080'})
    assert not _same_site(None, {'HTTP_HOST': 'localhost'})


def test_each_change_tells_the_people_it_concerns(push_on):
    app, db = push_on
    from app.qgen.models import CQuiz
    teacher, sam, kim = login(app, 'teach'), login(app, 'sam'), login(app, 'kim')
    t, s, k = connect(app, teacher), connect(app, sam), connect(app, kim)
    for sock in (t, s, k):
        sock.get_received()

    # a new quiz: everyone may see it
    vq = make_quiz(app, teacher)
    assert told(t) and told(s) and told(k)

    # assigned to sam: sam and the teachers, not kim
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    cq = CQuiz.query.filter_by(assignee=ids('sam')).one()
    assert told(t) and told(s) and not told(k)

    # sam starts and saves answers: the teachers see them come in; sam's page isn't told
    # about sam's own typing, and kim hears nothing
    sam.post('/quiz/take/{}/start'.format(cq.id))
    assert told(t) and told(s) and not told(k)
    sam.post('/quiz/take/{}/save'.format(cq.id), data={'Number1': '5', 'Number1_present': '1'})
    assert told(t) and not told(s) and not told(k)
    # saving the same answers again changes nothing: no one is told
    sam.post('/quiz/take/{}/save'.format(cq.id), data={'Number1': '5', 'Number1_present': '1'})
    assert not told(t) and not told(s)

    # handing in: sam (their other tabs too) and the teachers
    sam.post('/quiz/take/{}'.format(cq.id), data={'Number1': '4'})
    assert told(t) and told(s) and not told(k)

    # a message to kim: kim and the teachers
    teacher.post('/messages/send', data={'to': str(ids('kim')), 'body': 'Hello'},
                 headers={'Accept': 'application/json'})
    assert told(t) and told(k) and not told(s)


def test_check_ins_tell_teachers_only_when_it_matters(push_on):
    app, db = push_on
    from app.user.models import User
    teacher, sam, kim = login(app, 'teach'), login(app, 'sam'), login(app, 'kim')
    t, s, k = connect(app, teacher), connect(app, sam), connect(app, kim)
    sam.get('/mypage')  # sam's online now
    for sock in (t, s, k):
        sock.get_received()
    # a page saying "still here" for someone already online tells no one
    here(s)
    assert not told(t) and not told(s) and not told(k)
    # someone coming back after being away: the teachers' "online" lists change
    from datetime import datetime, timedelta
    db.session.get(User, ids('kim')).last_seen = datetime.now() - timedelta(days=1)
    db.session.commit()
    t.get_received()
    here(k)
    assert told(t) and not told(s)
    assert db.session.get(User, ids('kim')).online


def test_bookkeeping_and_undone_changes_tell_no_one(push_on):
    app, db = push_on
    from app.messages.models import Message
    teacher = login(app, 'teach')
    t = connect(app, teacher)
    t.get_received()
    # a wrong password is noted, but no page shows it
    app.test_client().post('/login', data={'username': 'sam', 'password': 'wrong'})
    assert not told(t)
    # a change that's rolled back never happened
    db.session.add(Message(student_id=ids('sam'), body='draft'))
    db.session.flush()
    db.session.rollback()
    assert not told(t)


def test_signing_out_closes_the_connection(push_on):
    app, db = push_on
    sam = login(app, 'sam')
    s = connect(app, sam)
    assert s.is_connected()
    sam.get('/logout')
    assert not s.is_connected()
    assert not connect(app, sam).is_connected()


def test_two_requests_marking_the_same_message_seen(app_db):
    """With instant updates a page reload and its check-in often arrive together, and both
    mark the new message seen: the second finds the first's row and carries on."""
    app, db = app_db
    from sqlalchemy import event, text
    from app.messages import services as M
    from app.messages.models import Message, MessageRead
    from app.user.models import User
    msg = Message(student_id=ids('sam'), from_teacher=False, body='Hi')
    db.session.add(msg)
    db.session.commit()
    teacher = db.session.get(User, ids('teach'))
    raced = []

    def other_tab(session, ctx, instances):
        #the other request saves its row just before this one's goes in
        if not raced:
            raced.append(True)
            session.execute(text('INSERT INTO message_read (message_id, user_id, cleared) VALUES (:m, :u, 0)'),
                            {'m': msg.id, 'u': teacher.id})
    event.listen(db.session, 'before_flush', other_tab)
    try:
        M._mark_for_teacher(teacher, [msg.id])
    finally:
        event.remove(db.session, 'before_flush', other_tab)
    assert raced and MessageRead.query.filter_by(message_id=msg.id).count() == 1
    assert db.session.get(Message, msg.id).seen_by_teacher
