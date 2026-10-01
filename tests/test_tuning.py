"""Technical settings: one page for the time spans and limits, admins only, and each
value really changes what the site does."""
from datetime import datetime, timedelta

from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)
from test_archive import ids

PAGE = '/settings/technical'


def form(**changes):
    """The page's form with every value as it is now, plus some changes."""
    from app import tuning
    data = {k: str(v) for k, v in tuning.values().items()}
    data.update({k: str(v) for k, v in changes.items()})
    return data


def set_values(**values):
    from app import tuning
    from app.user.models import User
    from app import db
    chosen = dict(tuning.values(), **values)
    tuning.save(chosen, db.session.get(User, ids('teach')))


def test_defaults_are_what_the_site_used_before(app_db):
    from app import tuning
    v = tuning.values()
    assert (v['online_window'], v['recently'], v['poll_seconds'], v['dashboard_seconds'], v['due_soon_days']) == (2, 60, 30, 30, 2)
    assert (v['list_grading'], v['list_handins'], v['list_assigned'], v['list_messages']) == (5, 10, 10, 5)
    assert (v['grace_minutes'], v['max_api_answer'], v['max_message']) == (2, 20000, 2000)
    assert (v['ai_hourly'], v['ai_model']) == (30, 'claude-opus-5')
    assert (v['min_password'], v['lockout_tries'], v['lockout_minutes'], v['token_days']) == (8, 10, 15, 90)
    assert tuning.seen_every() == timedelta(minutes=1)


def test_the_page_is_for_administrators(app_db):
    app, db = app_db
    from app.qgen.models import Setting
    sam = login(app, 'sam')
    for r in (sam.get(PAGE), sam.post(PAGE, data=form(online_window=9))):
        assert r.status_code == 302 and r.headers['Location'].endswith('/mypage')
    r = app.test_client().get(PAGE)
    assert r.status_code == 302 and '/login' in r.headers['Location']
    teacher = login(app, 'teach')
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        teacher.post(PAGE, data=dict(form(online_window=9), csrf_token='forged'))
    finally:
        app.config['WTF_CSRF_ENABLED'] = False
    assert Setting.query.filter(Setting.key.like('tune.%')).count() == 0
    page = teacher.get('/settings').data.decode()
    assert 'href="/settings/technical"' in page


def test_saving_checking_and_resetting(app_db):
    app, db = app_db
    from app import tuning
    teacher = login(app, 'teach')
    page = teacher.get(PAGE).data.decode()
    for label in ('Online window', 'Grace after a quiz', 'Requests per teacher per hour', 'Shortest password', 'claude-sonnet-5-5'):
        assert label in page
    r = teacher.post(PAGE, data=form(online_window=5, ai_model='claude-sonnet-5-5'), follow_redirects=True)
    assert 'Saved 2 changes.' in r.data.decode()
    assert tuning.get('online_window') == 5 and tuning.get('ai_model') == 'claude-sonnet-5-5'
    page = teacher.get(PAGE).data.decode()
    assert 'Changed' in page and 'name="reset" value="online_window"' in page and page.count('1 changed') == 2
    # out of range, not a number, an unknown model: nothing at all is saved
    for bad in ({'online_window': 31}, {'max_message': 'lots'}, {'ai_model': 'gpt-9'}, {'min_password': 3}):
        r = teacher.post(PAGE, data=form(recently=30, **bad))
        assert r.status_code == 400 and 'Nothing was saved' in r.data.decode()
        assert tuning.get('recently') == 60
    # the online window must cover two check-ins
    r = teacher.post(PAGE, data=form(online_window=2, poll_seconds=120))
    assert r.status_code == 400 and 'at least twice the check-in time (120 seconds)' in r.data.decode()
    assert tuning.get('poll_seconds') == 30
    # reset one, then all
    teacher.post(PAGE, data={'reset': 'online_window'})
    assert tuning.get('online_window') == 2 and tuning.get('ai_model') == 'claude-sonnet-5-5'
    teacher.post(PAGE, data={'reset': 'all'})
    assert tuning.get('ai_model') == 'claude-opus-5'
    # setting a value back to its default stores nothing
    from app.qgen.models import Setting
    teacher.post(PAGE, data=form(grace_minutes=4))
    teacher.post(PAGE, data=form(grace_minutes=2))
    assert Setting.query.filter(Setting.key.like('tune.%')).count() == 0


def test_a_broken_stored_value_means_the_default(app_db):
    from app import tuning
    from app.qgen.models import Setting
    Setting.put('tune.online_window', 'banana')
    Setting.put('tune.ai_model', 'not-a-model')
    Setting.put('tune.max_message', '999999999')
    assert tuning.get('online_window') == 2 and tuning.get('ai_model') == 'claude-opus-5' and tuning.get('max_message') == 2000


def test_online_settings_take_effect(app_db):
    app, db = app_db
    from app import tuning
    from app.user.models import User
    from app.qgen import dashboard as D
    now = datetime.now()
    sam = db.session.get(User, ids('sam'))
    sam.last_seen, sam.logged_in = now - timedelta(minutes=3), True
    db.session.commit()
    assert not sam.online and D.online(now) == []
    set_values(online_window=5)
    assert sam.online and [u.username for u in D.online(now)] == ['sam']
    assert tuning.seen_every() == timedelta(minutes=1)
    set_values(online_window=1, poll_seconds=20)
    assert tuning.seen_every() == timedelta(seconds=30)  # 60 - 20 - 10: stays inside the window
    # "active in the last ..."
    sam.last_seen = now - timedelta(minutes=50)
    db.session.commit()
    assert [u.username for u in D.recently_active(now)] == ['sam']
    set_values(recently=30)
    assert D.recently_active(now) == []
    # the pages are told how often to check in, and the Dashboard how often to refresh
    set_values(poll_seconds=45, dashboard_seconds=120, online_window=2)
    teacher = login(app, 'teach')
    page = teacher.get('/dashboard').data.decode()
    assert 'data-every="45000"' in page and 'data-every="120000"' in page
    assert 'checked every 45 seconds' in teacher.get('/dashboard/online').data.decode()


def test_dashboard_settings_take_effect(app_db):
    app, db = app_db
    from app.qgen import dashboard as D
    from app.qgen import services as S
    from app.qgen.models import VProblem, VQuiz
    from app.user.models import User
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Q', 'vplist': str(VProblem.query.one().id)})
    vq = VQuiz.query.one()
    now = datetime.now()
    sam = db.session.get(User, ids('sam'))
    for _ in range(4):
        S.create_cquiz(vq, sam, closes_at=now + timedelta(days=3))
    db.session.commit()
    assert D.counts(db.session.get(User, ids('teach')), now)['closing'] == 0
    set_values(due_soon_days=4, list_assigned=3)
    assert D.counts(db.session.get(User, ids('teach')), now)['closing'] == 4
    rows, total = D.out_now(now)
    assert len(rows) == 3 and total == 4


def test_grace_and_lengths_take_effect(app_db):
    app, db = app_db
    from app.qgen import services as S
    from app.qgen.models import VProblem, VQuiz
    from app.user.models import User
    from app.messages import services as M
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Q', 'vplist': str(VProblem.query.one().id)})
    now = datetime.now()
    cq = S.create_cquiz(VQuiz.query.one(), db.session.get(User, ids('sam')), closes_at=now - timedelta(minutes=3))
    db.session.commit()
    assert S.attempt_state(cq, now) == 'time_up'
    set_values(grace_minutes=5)
    assert S.attempt_state(cq, now) == 'open'
    # messages
    set_values(max_message=300)
    try:
        M.clean_body('x' * 301)
        assert False, 'too long was accepted'
    except M.MessageError as exc:
        assert 'under 300 characters' in str(exc)
    assert M.clean_body('x' * 300)
    # answers through the API
    from app.api.models import ApiToken
    set_values(max_api_answer=1000)
    token = ApiToken.issue(db.session.get(User, ids('sam')), 'test')[1]
    c = app.test_client()
    H = {'Authorization': 'Bearer ' + token}
    cq2 = S.create_cquiz(VQuiz.query.one(), db.session.get(User, ids('sam')))
    db.session.commit()
    r = c.put('/api/v2/my/attempts/{}/answers'.format(cq2.id), headers=H, json={'answers': {'1': '9' * 1001}})
    assert r.status_code == 400 and 'too long' in r.get_json()['error']['message']


def test_ai_settings_take_effect(app_db, monkeypatch):
    app, db = app_db
    from app.qgen import ai_helper
    from app.qgen.models import AICall
    from test_ai_helper import FakeClient, GOOD_PROBLEM
    fake = FakeClient(GOOD_PROBLEM)
    set_values(ai_model='claude-sonnet-5-5', ai_hourly=2)
    ai_helper.ask('key', 'problem', 'a train problem', client=fake)
    assert fake.calls[0]['model'] == 'claude-sonnet-5-5'
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    try:
        monkeypatch.setattr(ai_helper, '_client', lambda key: FakeClient(GOOD_PROBLEM))
        teacher = login(app, 'teach')
        body = {'text': 'a train problem'}
        assert teacher.post('/quiz/ai/problem', json=body).status_code == 200
        assert teacher.post('/quiz/ai/problem', json=body).status_code == 200
        r = teacher.post('/quiz/ai/problem', json=body)
        assert r.status_code == 429 and '2 times' in r.get_json()['error']
        assert AICall.query.count() == 2
    finally:
        app.config.pop('ANTHROPIC_API_KEY', None)


def test_security_settings_take_effect(app_db):
    app, db = app_db
    from app.qgen.models import Setting
    from app.user.models import User
    from app.api.models import ApiToken
    Setting.put('class_code', 'maple-7')
    set_values(min_password=12)
    c = app.test_client()
    r = c.post('/register', data={'class_code': 'maple-7', 'username': 'jo', 'email': '',
                                  'password': 'eleven-char', 'retype_password': 'eleven-char'})
    assert b'at least 12 characters' in r.data and User.query.filter_by(username='jo').count() == 0
    r = c.post('/register', data={'class_code': 'maple-7', 'username': 'jo', 'email': '',
                                  'password': 'twelve-chars', 'retype_password': 'twelve-chars'})
    assert r.status_code == 302 and User.query.filter_by(username='jo').count() == 1
    # the pause: 3 wrong passwords, 30 minutes
    set_values(lockout_tries=3, lockout_minutes=30)
    for _ in range(3):
        c.post('/login', data={'username': 'jo', 'password': 'wrong-guess'})
    r = c.post('/login', data={'username': 'jo', 'password': 'twelve-chars'}, follow_redirects=True)
    assert b'Please wait 30 minutes' in r.data
    # new tokens last the set number of days
    set_values(token_days=7)
    row, _ = ApiToken.issue(db.session.get(User, ids('teach')), 'test')
    assert timedelta(days=6, hours=23) < row.expires_at - datetime.now() <= timedelta(days=7)
