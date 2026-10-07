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
    assert '<h1>Dashboard</h1>' in page and 'href="/dashboard" class="active" aria-current="page">Dashboard</a>' in page
    assert 'class="brand" href="/dashboard"' in page and 'href="/mypage">My quizzes' in page
    # ?next= still wins; going to the login page when signed in goes home
    c2 = app.test_client()
    r = c2.post('/login?next=/quiz/listvq', data={'username': 'teach', 'password': 'pw-for-tests'})
    assert r.headers['Location'].endswith('/quiz/listvq')
    assert c2.get('/login').headers['Location'].endswith('/dashboard')

    s = app.test_client()
    r = s.post('/login', data={'username': 'sam', 'password': 'pw-for-tests'})
    assert r.headers['Location'].endswith('/home')
    assert s.get('/login').headers['Location'].endswith('/home')


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
        assert 'id="dash-live"' not in body and 'dash-counters' not in body and 'Site at a glance' not in body
    # signed out: log in first
    r = app.test_client().get('/dashboard')
    assert r.status_code == 302 and '/login' in r.headers['Location']
    # a student's pages never mention the Dashboard or who's online
    for url in ('/mypage', '/profile'):
        page = sam.get(url).data.decode()
        assert '/dashboard' not in page and 'Dashboard' not in page and 'online' not in page.lower().replace('inline', '')
        assert 'class="brand" href="/home"' in page


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
    sam = login(app, 'sam')
    vq = make_quiz(app, teacher)
    now = datetime.now()
    started = give(vq, 'sam', closes_at=now + timedelta(minutes=30))
    other = give(make_quiz(app, teacher, 'Other'), 'sam')
    S.start(started)
    S.start(other)
    for name in ('sam', 'kim'):
        u = db.session.get(User, ids(name))
        u.last_seen, u.logged_in = now, True
    db.session.commit()
    give(vq, 'kim')  # not started
    # started and online, but not on the quiz page: not listed
    assert D.taking_now(datetime.now()) == []
    # the quiz page open (its check-ins name it): only that quiz is listed
    sam.get('/messages/poll?watch=attempt:{}'.format(started.id))
    rows = D.taking_now(datetime.now())
    assert [(r['cq'].taker.username, r['cq'].vquiz.title) for r in rows] == [('sam', 'Week 1')]
    assert timedelta(minutes=29) < rows[0]['left'] <= timedelta(minutes=30)
    # on another page now: off the list straight away (opening it, before its first check-in)
    sam.get('/home', headers={'Sec-Fetch-Mode': 'navigate'})
    assert D.taking_now(datetime.now()) == []
    sam.get('/messages/poll?watch=attempt:{}'.format(started.id))
    sam.get('/messages/poll?watch=home')
    assert D.taking_now(datetime.now()) == []
    # opening the quiz page counts; its check-ins stop (tab closed or hidden): off after the online window
    sam.get('/quiz/take/{}'.format(started.id))
    assert len(D.taking_now(datetime.now())) == 1
    assert D.taking_now(datetime.now() + timedelta(minutes=5)) == []
    # a teacher looking at sam's quiz isn't sam taking it, nor the teacher
    sam.get('/messages/poll?watch=home')
    teacher.get('/messages/poll?watch=attempt:{}'.format(started.id))
    assert D.taking_now(datetime.now()) == []
    # handed in: not listed
    sam.get('/messages/poll?watch=attempt:{}'.format(started.id))
    with app.test_request_context():
        S.submit(started, {1: '4'})
    assert D.taking_now(datetime.now()) == []
    # it shows on the page (the quiz's name opens sam's quiz as it is), and refreshes on its own
    sam.get('/messages/poll?watch=attempt:{}'.format(other.id))
    part = teacher.get('/dashboard/now').data.decode()
    assert 'Taking a quiz' in part and '<strong>sam</strong>' in part
    assert 'href="/quiz/take/{}"'.format(other.id) in part and '“Other”</a>' in part
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


def test_student_messages_are_counted_but_not_listed(app_db):
    # the Dashboard has no messages box; it only counts unread ones, and opening it marks nothing read
    app, db = app_db
    from app.messages.models import MessageRead
    sam = login(app, 'sam')
    sam.post('/messages/reply', data={'body': 'First question'})
    teacher = login(app, 'teach')
    before = MessageRead.query.count()
    page = teacher.get('/dashboard').data.decode()
    assert 'First question' not in page and 'Recent messages' not in page and 'data-box="messages"' not in page
    # the order: Right now beside Site at a glance, then Assigned, then grading and hand-ins
    order = [page.index('data-box="{}"'.format(k)) for k in ('now', 'glance', 'out', 'queue', 'handins')]
    assert order == sorted(order) and page.index('dash-counters') < order[0]
    assert MessageRead.query.count() == before
    assert '1</span><span>unread message</span>' in page


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
    for key in ('now', 'glance', 'out', 'queue', 'handins'):
        assert 'data-box="{}" open>'.format(key) in page
    assert 'data-dash-boxes="open"' in page and 'data-dash-boxes="close"' in page and 'js/dashboard.js' in page
    assert 'data-box="now" open>' in teacher.get('/dashboard/now').data.decode()


def test_the_whole_dashboard_refreshes(app_db):
    # a hand-in after the Dashboard was opened shows on its next refresh, in every box
    app, db = app_db
    from app.qgen import services as S
    teacher = login(app, 'teach')
    vq = make_quiz(app, teacher, 'variables1')
    cq = give(vq, 'sam')
    page = teacher.get('/dashboard').data.decode()
    assert 'data-url="/dashboard/now"' in page and 'Nothing handed in yet.' in page
    with app.test_request_context():
        S.submit(cq, {1: '4'})
    part = teacher.get('/dashboard/now').data.decode()
    assert 'Nothing handed in yet.' not in part and '/quiz/take/{}'.format(cq.id) in part  # Recent hand-ins
    for key in ('now', 'glance', 'out', 'queue', 'handins'):
        assert 'data-box="{}" open>'.format(key) in part


def test_no_quiz_progress_or_students_to_check(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    page = teacher.get('/dashboard').data.decode()
    assert 'Quiz progress' not in page and 'Students to check on' not in page
    assert 'data-box="check"' not in page and 'data-box="progress"' not in page


def test_assigned_but_not_handed_in(app_db):
    app, db = app_db
    from app.qgen import dashboard as D
    from app.qgen import services as S
    teacher = login(app, 'teach')
    now = datetime.now()
    vq = make_quiz(app, teacher, 'Fractions')
    fresh = give(vq, 'sam', closes_at=now + timedelta(days=3))
    going = give(vq, 'kim')
    S.start(going)
    later = give(vq, 'kim', opens_at=now + timedelta(days=1))
    done = give(vq, 'sam')
    with app.test_request_context():
        S.submit(done, {1: '4'})
    rows, total = D.out_now(now)
    assert total == 3 and done.id not in [r['cq'].id for r in rows]
    states = {r['cq'].id: r['state'] for r in rows}
    assert states == {fresh.id: 'new', going.id: 'started', later.id: 'not_open'}
    assert len(D.out_now(now, limit=2)[0]) == 2
    page = teacher.get('/dashboard').data.decode()
    assert 'Assigned, not handed in yet' in page and 'Not started' in page and 'In progress' in page and 'Opens tomorrow' in page


def test_logging_out_takes_you_off_online(app_db):
    # logging out ends "online" at once (the logout click itself doesn't count as being
    # here); still signed in on another device, the next request brings you back
    app, db = app_db
    from app.user.models import User
    from app.qgen import dashboard as D
    teacher = login(app, 'teach')
    phone, laptop = login(app, 'sam'), login(app, 'sam')
    phone.get('/mypage')
    laptop.get('/mypage')
    now = datetime.now()
    assert 'sam' in [u.username for u in D.online(now)]
    phone.get('/logout')
    db.session.expire_all()
    sam = db.session.get(User, ids('sam'))
    assert not sam.online and sam.seen_label() == 'just now'
    assert 'sam' not in [u.username for u in D.online(datetime.now())]
    assert 'sam' in [u.username for u in D.recently_active(datetime.now())]
    part = teacher.get('/dashboard/online').data.decode()
    assert part.index('Active in the last hour') < part.index('sam')
    assert teacher.get('/messages/poll').get_json()['online'] == 1  # just the teacher
    # the laptop is still signed in: its next request counts
    laptop.get('/messages/poll')
    db.session.expire_all()
    assert db.session.get(User, ids('sam')).online


def test_pinned_messages_box(app_db):
    app, db = app_db
    import re
    teach, sam = login(app, 'teach'), login(app, 'sam')
    page = teach.get('/dashboard').data.decode()
    assert 'class="box-title">Pinned messages</h2><span class="badge box-count">0 messages</span>' in page and 'Nothing is pinned.' in page
    teach.post('/messages/send', data={'to': 'all', 'body': 'No class Friday', 'pin': '1'})
    teach.post('/messages/send', data={'to': str(ids('sam')), 'body': 'See me after class', 'pin': '1'})
    teach.post('/messages/send', data={'to': 'all', 'body': 'Not pinned'})
    sam.get('/messages/panel')  # sam reads his messages
    page = teach.get('/dashboard/now').data.decode()
    assert 'class="box-title">Pinned messages</h2><span class="badge box-count">2 messages</span>' in page and 'Not pinned' not in page
    assert re.search(r'No class Friday</span>.*?to every student\s*· read by 1 of 2', page, re.S)
    assert re.search(r'See me after class</span>.*?to sam\s*· read ·', page, re.S)
    # Unpin from the Dashboard: every copy
    from app.messages.models import Message
    mid = Message.query.filter_by(body='No class Friday').first().id
    teach.post('/messages/pin/{}'.format(mid), data={'pinned': '0'})
    assert Message.query.filter_by(body='No class Friday', pinned=True).count() == 0
    assert 'class="box-title">Pinned messages</h2><span class="badge box-count">1 message</span>' in teach.get('/dashboard/now').data.decode()
