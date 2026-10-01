"""The administrators' Dashboard: where teachers land, what it shows, and that it's
theirs alone."""
from datetime import datetime, timedelta

from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)
from test_archive import ids


def make_quiz(app, teacher, title='Week 1', essay=False):
    from app.qgen.models import VProblem, VQuiz
    if essay:
        teacher.post('/quiz/makevprob', data=problem_form('essay', title + ' essay', 'Explain photosynthesis.'))
    else:
        teacher.post('/quiz/makevprob', data=problem_form('numeric', title + ' sum', 'What is 2 + 2?', '4', []))
    vp = VProblem.query.order_by(VProblem.id.desc()).first()
    teacher.post('/quiz/makevquiz', data={'title': title, 'vplist': str(vp.id), 'shuffle_order': ''})
    return VQuiz.query.filter_by(title=title).one()


def give(vq, student, **kw):
    from app.qgen import services as S
    from app.user.models import User
    from app import db
    return S.create_cquiz(vq, db.session.get(User, ids(student)), **kw)


def test_teachers_land_on_the_dashboard_and_students_dont(app_db):
    app, db = app_db
    c = app.test_client()
    r = c.post('/login', data={'username': 'teach', 'password': 'pw-for-tests'})
    assert r.headers['Location'].endswith('/dashboard')
    page = c.get('/dashboard').data.decode()
    assert '<h1>Dashboard</h1>' in page and 'href="/dashboard">Dashboard</a>' in page
    assert 'class="brand" href="/dashboard"' in page and 'href="/mypage">My quizzes</a>' in page
    # ?next= still wins; going to the login page when signed in goes home
    c2 = app.test_client()
    r = c2.post('/login?next=/quiz/listvq', data={'username': 'teach', 'password': 'pw-for-tests'})
    assert r.headers['Location'].endswith('/quiz/listvq')
    assert c2.get('/login').headers['Location'].endswith('/dashboard')

    s = app.test_client()
    r = s.post('/login', data={'username': 'sam', 'password': 'pw-for-tests'})
    assert r.headers['Location'].endswith('/mypage')
    assert s.get('/login').headers['Location'].endswith('/mypage')


def test_the_dashboard_is_for_administrators_only(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    make_quiz(app, teacher)
    sam = login(app, 'sam')
    for url in ('/dashboard', '/dashboard/now'):
        r = sam.get(url)
        assert r.status_code == 302 and r.headers['Location'].endswith('/mypage')
        body = sam.get(url, follow_redirects=True).data.decode()
        assert 'That page is for administrators only.' in body
        assert 'id="dash-now"' not in body and 'dash-counters' not in body and 'Site at a glance' not in body
    # signed out: log in first
    r = app.test_client().get('/dashboard')
    assert r.status_code == 302 and '/login' in r.headers['Location']
    # a student's pages never mention the Dashboard or who's online
    for url in ('/mypage', '/profile'):
        page = sam.get(url).data.decode()
        assert '/dashboard' not in page and 'Dashboard' not in page and 'online' not in page.lower().replace('inline', '')
        assert 'class="brand" href="/mypage"' in page


def test_last_seen_and_who_is_online(app_db):
    app, db = app_db
    from app.user.models import User, note_seen
    from app.qgen import dashboard as D
    sam = login(app, 'sam')
    sam.get('/mypage')
    u = db.session.get(User, ids('sam'))
    first = u.last_seen
    assert first is not None and u.online
    # not rewritten within the minute
    sam.get('/mypage')
    db.session.expire_all()
    assert db.session.get(User, ids('sam')).last_seen == first
    note_seen(u, first + timedelta(seconds=61))
    assert db.session.get(User, ids('sam')).last_seen == first + timedelta(seconds=61)
    now = first + timedelta(seconds=61)
    assert [x.username for x in D.online(now)] == ['sam']
    assert D.online(now + timedelta(minutes=3)) == []
    # static files don't count; nor do signed-out visitors
    assert db.session.get(User, ids('kim')).last_seen is None


def test_taking_a_quiz_right_now(app_db):
    app, db = app_db
    from app.qgen import dashboard as D
    from app.qgen import services as S
    from app.user.models import User
    teacher = login(app, 'teach')
    vq = make_quiz(app, teacher)
    now = datetime.now()
    started = give(vq, 'sam', closes_at=now + timedelta(minutes=30))
    S.start(started)
    for name in ('sam', 'kim'):
        db.session.get(User, ids(name)).last_seen = now
    db.session.commit()
    give(vq, 'kim')  # not started
    rows = D.taking_now(now)
    assert [(r['cq'].taker.username, r['cq'].vquiz.title) for r in rows] == [('sam', 'Week 1')]
    assert timedelta(minutes=29) < rows[0]['left'] <= timedelta(minutes=30)
    # not online: not listed
    assert D.taking_now(now + timedelta(minutes=5)) == []
    # handed in: not listed
    with app.test_request_context():
        S.submit(started, {1: '4'})
    assert D.taking_now(now) == []
    # it shows on the page, and the live part refreshes on its own
    db.session.get(User, ids('sam')).last_seen = datetime.now()
    later = give(vq, 'sam')
    S.start(later)
    db.session.commit()
    part = teacher.get('/dashboard/now').data.decode()
    assert 'Taking a quiz' in part and '<strong>sam</strong>' in part and '“Week 1”' in part
    assert 'data-url="/dashboard/now"' in teacher.get('/dashboard').data.decode()


def test_grading_queue_and_recent_handins(app_db):
    app, db = app_db
    from app.qgen import dashboard as D
    from app.qgen import services as S
    teacher = login(app, 'teach')
    essay = make_quiz(app, teacher, 'Essays', essay=True)
    sums = make_quiz(app, teacher, 'Sums')
    t0 = datetime.now() - timedelta(hours=3)
    a = give(essay, 'sam')
    b = give(essay, 'kim')
    c = give(sums, 'sam')
    with app.test_request_context():
        S.submit(a, {1: 'Light makes sugar.'})
        S.submit(b, {1: 'Plants eat sun.'})
        S.submit(c, {1: '4'})
    a.compdate, b.compdate, c.compdate = t0 + timedelta(minutes=10), t0, t0 + timedelta(minutes=20)
    db.session.commit()
    queue, waiting = D.grading_queue()
    assert [q.id for q in queue] == [b.id, a.id] and waiting == 2  # oldest first, as on Review
    assert [q.id for q in D.grading_queue(limit=1)[0]] == [b.id]
    assert [h.id for h in D.recent_handins()] == [c.id, a.id, b.id]
    page = teacher.get('/dashboard').data.decode()
    assert '/quiz/review/{}'.format(b.id) in page and '/quiz/take/{}'.format(c.id) in page
    assert 'badge-ok">100%' in page and 'being graded' in page


def test_students_to_check_on(app_db):
    app, db = app_db
    from app.qgen import dashboard as D
    from app.qgen import services as S
    teacher = login(app, 'teach')
    now = datetime.now()
    soon = make_quiz(app, teacher, 'Soon')
    later = make_quiz(app, teacher, 'Later')
    gone = make_quiz(app, teacher, 'Gone')
    low = make_quiz(app, teacher, 'Low')
    give(soon, 'sam', closes_at=now + timedelta(days=1))
    give(later, 'sam', closes_at=now + timedelta(days=5))
    missed = give(gone, 'kim', closes_at=now - timedelta(days=1))
    with app.test_request_context():
        S.close_expired(now)
    assert db.session.get(type(missed), missed.id).completed  # handed in, empty, by the clock
    bad = give(low, 'kim')
    with app.test_request_context():
        S.submit(bad, {1: '5'})  # 0%
    # the teacher has a quiz too: teachers are never listed
    give(soon, 'teach', closes_at=now + timedelta(hours=2))
    rows = {r['student'].username: r['reasons'] for r in D.students_to_check(now)}
    assert set(rows) == {'sam', 'kim'}
    assert len(rows['sam']) == 1 and rows['sam'][0].startswith('Hasn\'t started “Soon” (closes ')
    assert any(r.startswith('Missed “Gone”') for r in rows['kim'])
    assert any(r.startswith('Average score 0% over') for r in rows['kim'])
    # the counted score follows the retake rule: a good retake under "latest" clears it
    with app.test_request_context():
        kim_low = S.retake(bad)
        S.submit(kim_low, {1: '4'})
    S.set_retake_rule(bad, 'latest')
    rows = {r['student'].username: r['reasons'] for r in D.students_to_check(now)}
    assert not any(r.startswith('Average') for r in rows['kim'])


def test_quiz_progress(app_db):
    app, db = app_db
    from app.qgen import dashboard as D
    from app.qgen import services as S
    teacher = login(app, 'teach')
    now = datetime.now()
    vq = make_quiz(app, teacher, 'Week 2')
    old = make_quiz(app, teacher, 'Long ago')
    a = give(vq, 'sam', closes_at=now + timedelta(days=3))
    give(vq, 'kim', closes_at=now + timedelta(days=1))
    with app.test_request_context():
        S.submit(a, {1: '4'})
    ancient = give(old, 'sam')
    with app.test_request_context():
        S.submit(ancient, {1: '4'})
    ancient.compdate = now - timedelta(days=30)
    db.session.commit()
    rows = D.quiz_progress(now)
    assert [r['vquiz'].title for r in rows] == ['Week 2']
    r = rows[0]
    assert (r['assigned'], r['finished'], r['waiting'], r['average']) == (2, 1, 0, 100.0)
    assert now + timedelta(hours=23) < r['closes'] <= now + timedelta(days=1)


def test_recent_messages_are_shown_but_not_marked_read(app_db):
    app, db = app_db
    from app.messages.models import Message, MessageRead
    sam = login(app, 'sam')
    for text in ('First question', 'Second question'):
        sam.post('/messages/reply', data={'body': text})
    teacher = login(app, 'teach')
    before = MessageRead.query.count()
    page = teacher.get('/dashboard').data.decode()
    assert page.index('Second question') < page.index('First question')
    assert 'dash-unread' in page and '>new</span>' in page
    assert MessageRead.query.count() == before
    assert Message.query.filter_by(from_teacher=False, kind='message').count() == 2


def test_site_at_a_glance(app_db):
    app, db = app_db
    from app.qgen import dashboard as D
    from app.qgen.models import AICall, Setting
    teacher = login(app, 'teach')
    make_quiz(app, teacher)
    now = datetime.now()
    g = D.site_glance(now)
    assert (g['students'], g['teachers'], g['problems'], g['quizzes'], g['archived']) == (2, 1, 1, 1, 0)
    assert g['signup_open'] is False and g['ai_calls'] == 0
    Setting.put('class_code', 'ABC')
    db.session.add_all([AICall(user_id=ids('teach'), kind='problem', ok=True, input_tokens=100, output_tokens=50, created=now),
                        AICall(user_id=ids('teach'), kind='problem', ok=True, input_tokens=1, output_tokens=1,
                               created=now.replace(day=1) - timedelta(days=1))])
    db.session.commit()
    g = D.site_glance(now)
    assert g['signup_open'] is True and g['ai_calls'] == 1 and g['ai_tokens'] == 150
    page = teacher.get('/dashboard').data.decode()
    assert 'Site at a glance' in page and 'badge-ok">open' in page


def test_who_is_logged_in(app_db):
    # online now (you included), active in the last hour, "last seen" on Users, and the
    # top bar's count: all for teachers only
    app, db = app_db
    from app.user.models import User
    from app.qgen import dashboard as D
    now = datetime.now()
    teacher = login(app, 'teach')
    teacher.get('/dashboard')
    sam, kim = db.session.get(User, ids('sam')), db.session.get(User, ids('kim'))
    sam.last_seen = now - timedelta(minutes=12)
    kim.last_seen = now - timedelta(days=3)
    db.session.commit()
    assert sam.seen_label(now) == '12 min ago' and not sam.online
    assert kim.seen_label(now) == '{:%b} {}'.format(kim.last_seen, kim.last_seen.day)
    assert User(username='x').seen_label(now) == 'never'
    assert [u.username for u in D.recently_active(now)] == ['sam']

    page = teacher.get('/dashboard').data.decode()
    assert 'Online now' in page and '(you)' in page and 'Active in the last hour' in page and '12 min ago' in page
    part = teacher.get('/dashboard/online').data.decode()
    assert 'teach' in part and '(you)' in part and 'sam' in part and 'kim' not in part
    users = teacher.get('/userdet').data.decode()
    assert '<th>Last seen</th>' in users and 'online now' in users and '12 min ago' in users
    assert '<span class="nav-online">1</span>' in page  # the top bar: just this teacher so far
    assert teacher.get('/messages/poll').get_json()['online'] == 1

    s = login(app, 'sam')
    mine = s.get('/mypage').data.decode()
    assert 'online-menu' not in mine and 'nav-online' not in mine and 'js/online.js' not in mine
    assert s.get('/messages/poll').get_json()['online'] is None
    r = s.get('/dashboard/online')
    assert r.status_code == 302 and r.headers['Location'].endswith('/mypage')


def test_dashboard_boxes_open_and_close(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    page = teacher.get('/dashboard').data.decode()
    for key in ('now', 'queue', 'handins', 'check', 'messages', 'progress', 'glance'):
        assert 'data-box="{}" open>'.format(key) in page
    assert 'data-dash-boxes="open"' in page and 'data-dash-boxes="close"' in page and 'js/dashboard.js' in page
    assert 'data-box="now" open>' in teacher.get('/dashboard/now').data.decode()
