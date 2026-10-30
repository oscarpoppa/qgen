"""Late and expired attempts (the clocks and the fish bones) and the Pending Quizzes page (it was Open Quizzes) (the owner, 2026-10-29, To do 75)."""
from datetime import datetime, timedelta

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_assign_pages import ids, quiz_of, copies


def test_late_and_urgency():
    from app.qgen.models import CQuiz
    now = datetime(2026, 10, 28, 12, 0)
    day = timedelta(days=1)
    assert CQuiz(create_date=now - day - timedelta(minutes=1)).state_kind(now) == 'late-new'
    assert CQuiz(create_date=now - timedelta(hours=20)).state_kind(now) == 'new'
    #(counted from when it opened, not when it was assigned)
    assert CQuiz(create_date=now - 3 * day, opens_at=now - timedelta(hours=2)).late_since(now) is None
    assert CQuiz(create_date=now - 3 * day, startdate=now - 2 * day).state_kind(now) == 'late-going'
    assert CQuiz(create_date=now - 3 * day, startdate=now - timedelta(hours=3)).state_kind(now) == 'started'
    #waiting for grading or handed in: never late
    assert CQuiz(create_date=now - 3 * day, startdate=now - 2 * day, needs_review=True).late_since(now) is None
    assert CQuiz(create_date=now - 3 * day, startdate=now - 2 * day, completed=True).late_since(now) is None
    kinds = [CQuiz(create_date=now - 2 * day), CQuiz(create_date=now - 3 * day, startdate=now - 2 * day),
             CQuiz(expired='closed', completed=True), CQuiz(create_date=now), CQuiz(create_date=now, startdate=now),
             CQuiz(create_date=now, startdate=now, needs_review=True), CQuiz(create_date=now, startdate=now, completed=True)]
    assert [cq.urgency(now) for cq in kinds] == [1, 2, 3, 4, 5, 6, 7]


def test_words():
    from app.qgen.models import CQuiz
    now = datetime(2026, 10, 28, 12, 0)
    assert CQuiz(create_date=datetime(2026, 10, 25, 8, 0)).state_label(now=now) == 'Late: not started since it opened Oct 25'
    assert CQuiz(create_date=datetime(2026, 10, 25, 8, 0), startdate=datetime(2026, 10, 26, 9, 10)).state_label(now=now) == \
        'Late: started Oct 26 9:10 AM, not handed in'
    dead = CQuiz(expired='closed', completed=True, score=0.0)
    assert dead.state_label(own=True) == 'Expired: closed before you started it; handed in automatically · 0%'
    assert dead.state_label() == 'Expired: closed before he/she started it; handed in automatically · 0%'
    assert dead.marked_kind() == 'expired-new'
    timed = CQuiz(expired='time', completed=True, score=40.0, startdate=now)
    assert timed.state_label() == 'Expired: handed in automatically when its time ran out · 40%'
    assert timed.marked_kind() == 'expired-going'
    assert CQuiz(expired='closed', completed=True, score=40.0, startdate=now).state_label() == \
        'Expired: handed in automatically when it closed · 40%'
    assert CQuiz(create_date=now).state_label(now=now) is None


def _given(app, db, title):
    teacher = login(app, 'teach')
    vq, _probs = quiz_of(teacher, title)
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    return teacher, copies(vq)[0]


def test_expired_by_closing_and_by_time(app_db):
    from app.qgen import services as S
    from app.qgen.models import CQuiz
    app, db = app_db
    _teacher, closed = _given(app, db, 'E1')
    closed.closes_at = datetime.now() - timedelta(minutes=30)
    _teacher, timed = _given(app, db, 'E2')
    timed.time_limit, timed.startdate = 10, datetime.now() - timedelta(hours=1)
    db.session.commit()
    with app.test_request_context():
        assert S.close_expired() == 2
    assert db.session.get(CQuiz, closed.id).expired == 'closed'
    assert db.session.get(CQuiz, timed.id).expired == 'time'


def test_open_quizzes_page(app_db):
    from app.qgen import services as S
    from app.qgen.models import CQuiz
    app, db = app_db
    teacher, late = _given(app, db, 'O1')
    late.create_date = datetime.now() - timedelta(days=2)
    _t, dead = _given(app, db, 'O2')
    dead.closes_at = datetime.now() - timedelta(minutes=5)
    db.session.commit()
    with app.test_request_context():
        S.close_expired()
    page = teacher.get('/quiz/open').data.decode()
    assert '<h1>Pending Quizzes</h1>' in page and 'All Pending' in page and 'Waiting for Grading' in page
    assert 'title="Late: not started since it opened' in page
    assert 'Expired: closed before he/she started it; handed in automatically · 0%' in page
    assert 'Q O1' in teacher.get('/quiz/open?folder=late').data.decode()
    assert 'Q O1' not in teacher.get('/quiz/open?folder=expired').data.decode()
    #the student opening an expired attempt doesn't take it off; a teacher opening it does (the fish stays on its line)
    login(app, 'sam').get('/quiz/take/{}'.format(dead.id))
    assert not db.session.get(CQuiz, dead.id).expired_seen
    teacher.get('/quiz/take/{}'.format(dead.id))
    assert db.session.get(CQuiz, dead.id).expired_seen
    assert 'Q O2' not in teacher.get('/quiz/open').data.decode()
    assert 'Expired: closed before he/she started it' in teacher.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert 'Nothing here right now.' in teacher.get('/quiz/open?folder=review').data.decode()


def test_open_quizzes_is_for_teachers(app_db):
    app, _db = app_db
    r = login(app, 'sam').get('/quiz/open')
    assert r.status_code in (302, 403)


def test_close_expired_command_hands_in_a_picture_question(app_db):
    #(the nightly command crashed on url_for in the transcript outside a page request: found 2026-10-29)
    from app.qgen.models import CQuiz
    app, db = app_db
    _teacher, cq = _given(app, db, 'P1')
    cq.time_limit, cq.startdate = 10, datetime.now() - timedelta(hours=1)
    for cp in cq.cproblems:
        cp.vproblem.image = 'pic.png'
    db.session.commit()
    out = app.test_cli_runner().invoke(args=['close-expired'])
    assert out.exception is None, out.output
    assert 'closed 1 quiz attempt(s)' in out.output
    assert db.session.get(CQuiz, cq.id).expired == 'time'


def test_open_quizzes_links_to_student_history_and_back(app_db):
    app, db = app_db
    teacher, cq = _given(app, db, 'L1')
    page = teacher.get('/quiz/open').data.decode()
    assert 'href="/quiz/listuser/{}?folder=none&amp;show={}"'.format(cq.assignee, cq.vquiz_id) in page
    history = teacher.get('/quiz/listuser/{}?show={}'.format(cq.assignee, cq.vquiz_id)).data.decode()
    assert ' data-show>' in history
    #(People in his/her own folder: none here, so Uncategorized)
    assert 'href="/userdet?folder=main&amp;show={}"'.format(cq.assignee) in history


def test_student_history_attempt_lines_show_time_and_assigned(app_db):
    from datetime import datetime
    app, db = app_db
    teacher, cq = _given(app, db, 'W1')
    cq.create_date, cq.startdate = datetime(2026, 10, 28, 14, 52), datetime(2026, 10, 29, 21, 16)
    db.session.commit()
    page = teacher.get('/quiz/listuser/{}'.format(cq.assignee)).data.decode()
    assert 'started Oct 29, 9:16 PM' in page and 'assigned Oct 28, 2:52 PM' in page
