"""A student writes to all their teachers or to one of them; a message to one teacher is
seen (and counted) only by that teacher."""
from datetime import datetime

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_archive import ids

FETCH = {'X-Requested-With': 'fetch'}


def second_teacher(db):
    from app.user.models import User
    t2 = User(username='lee', is_admin=True)
    t2.set_password('pw-for-tests')
    db.session.add(t2)
    db.session.commit()
    return t2


def test_a_message_to_one_teacher_is_only_theirs(app_db):
    app, db = app_db
    from app.messages.models import Message
    second_teacher(db)
    teach, lee, sam = login(app, 'teach'), login(app, 'lee'), login(app, 'sam')
    r = sam.post('/messages/reply', data={'body': 'Only for teach', 'to': str(ids('teach'))}, headers=FETCH)
    assert r.get_json() == {'ok': True}
    sam.post('/messages/reply', data={'body': 'For everyone', 'to': 'all'}, headers=FETCH)
    private = Message.query.filter_by(body='Only for teach').one()
    assert not private.to_all and [t.username for t in private.recipients] == ['teach']

    # teach: counted, popped up, listed everywhere, labeled
    poll = teach.get('/messages/poll').get_json()
    assert poll['unread'] == 2 and poll['message_preview']['text'] == 'For everyone'
    for url in ('/messages/panel', '/messages/panel?student={}'.format(ids('sam')), '/messages/{}'.format(ids('sam'))):
        page = teach.get(url).data.decode()
        assert 'Only for teach' in page and 'For everyone' in page, url
    assert 'to you only' in teach.get('/messages/panel').data.decode()

    # lee: never sees it, isn't told about it, and can't delete it
    assert lee.get('/messages/poll').get_json()['unread'] == 1
    for url in ('/messages/panel', '/messages/panel?student={}'.format(ids('sam')), '/messages/{}'.format(ids('sam')),
                '/messages', '/dashboard'):
        page = lee.get(url).data.decode()
        assert 'Only for teach' not in page, url
    assert 'For everyone' in lee.get('/messages/{}'.format(ids('sam'))).data.decode()
    lee.post('/messages/delete/{}'.format(private.id), headers=FETCH)
    assert db.session.get(Message, private.id) is not None
    assert lee.get('/messages/poll').get_json()['unread'] == 0  # reading what lee can see clears lee's count
    db.session.expire_all()
    from app.messages.models import MessageRead
    assert not MessageRead.query.filter_by(message_id=private.id, user_id=ids('lee')).count()  # never marked for lee


def test_the_students_panel_picks_a_teacher(app_db):
    app, db = app_db
    from app.user.models import User
    lee = second_teacher(db)
    lee.last_seen, lee.logged_in = datetime.now(), True  # online
    db.session.commit()
    teach, leec, sam = login(app, 'teach'), login(app, 'lee'), login(app, 'sam')
    teach.post('/messages/send', data={'to': str(ids('sam')), 'body': 'From teach'}, headers=FETCH)
    leec.post('/messages/send', data={'to': str(ids('sam')), 'body': 'From lee'}, headers=FETCH)
    sam.post('/messages/reply', data={'body': 'Sam to lee', 'to': str(ids('lee'))}, headers=FETCH)
    sam.post('/messages/reply', data={'body': 'Sam to all', 'to': 'all'}, headers=FETCH)
    t = User.query.filter_by(username='teach').one()
    t.last_seen = datetime(2026, 1, 1)  # teach has gone away; lee is still here
    db.session.commit()
    # every teacher listed, online ones first and marked, with what's still unread from each
    # (lee's conversation opened first: teach's message is still waiting)
    first = sam.get('/messages/panel?student={}'.format(ids('lee'))).data.decode()
    assert first.index('>● lee (online)<') < first.index('>teach (1 new)<')
    panel = sam.get('/messages/panel').data.decode()  # all of them: everything read now
    assert '>● lee (online)<' in panel and '>teach<' in panel
    # writing: every teacher checked when looking at all of them
    assert 'All my teachers' in panel and 'name="to_checked"' in panel
    for name in ('teach', 'lee'):
        assert 'name="to" value="{}" checked'.format(ids(name)) in panel
    for text in ('From teach', 'From lee', 'Sam to lee', 'Sam to all'):
        assert text in panel
    assert 'to lee only' in panel and 'to all teachers' in panel
    # one teacher: that conversation, and writing goes only to them
    with_lee = sam.get('/messages/panel?student={}'.format(ids('lee'))).data.decode()
    assert 'From lee' in with_lee and 'Sam to lee' in with_lee and 'Sam to all' in with_lee
    assert 'From teach' not in with_lee
    assert 'name="to" value="{}" checked'.format(ids('lee')) in with_lee  # only lee checked
    assert 'name="to" value="{}">'.format(ids('teach')) in with_lee and 'Only the teachers you check will see it' in with_lee
    with_teach = sam.get('/messages/panel?student={}'.format(ids('teach'))).data.decode()
    assert 'Sam to lee' not in with_teach and 'From teach' in with_teach
    # nonsense choices: the all-teachers view; and nobody but a teacher can be written to
    assert 'All my teachers</option>' in sam.get('/messages/panel?student={}'.format(ids('kim'))).data.decode()
    for bad in (str(ids('kim')), 'x', '99999'):
        r = sam.post('/messages/reply', data={'body': 'Hi', 'to': bad}, headers=FETCH)
        assert r.status_code == 400 and 'choose one of your teachers' in r.get_json()['error']
    # the student's own open panel follows a teacher coming online
    state = sam.get('/messages/poll').get_json()['messages_state']
    t.last_seen, t.logged_in = datetime.now(), True
    db.session.commit()
    assert sam.get('/messages/poll').get_json()['messages_state'] != state


def test_the_app_api_follows_the_same_rules(app_db):
    app, db = app_db
    from app.api.models import ApiToken
    from app.user.models import User
    second_teacher(db)
    token = lambda name: {'Authorization': 'Bearer ' + ApiToken.issue(User.query.filter_by(username=name).one(), 't')[1]}
    c = app.test_client()
    r = c.post('/api/v2/my/messages', headers=token('sam'), json={'body': 'Private to lee', 'to': ids('lee')})
    assert r.status_code == 201
    got = c.get('/api/v2/my/messages', headers=token('sam')).get_json()
    assert {t['username'] for t in got['teachers']} == {'teach', 'lee'}
    assert got['messages'][-1]['to'] == ['lee']
    lee_view = c.get('/api/v2/messages/{}'.format(ids('sam')), headers=token('lee')).get_json()['messages']
    teach_view = c.get('/api/v2/messages/{}'.format(ids('sam')), headers=token('teach')).get_json()['messages']
    assert [m['body'] for m in lee_view] == ['Private to lee'] and teach_view == []
    r = c.post('/api/v2/my/messages', headers=token('sam'), json={'body': 'Hi', 'to': ids('kim')})
    assert r.status_code == 422


def test_a_student_writes_to_several_teachers(app_db):
    """Checked teachers only; all of them checked is the same as "all"; none checked is refused."""
    app, db = app_db
    from app.messages.models import Message
    from app.user.models import User
    second_teacher(db)
    t3 = User(username='ray', is_admin=True)
    t3.set_password('pw-for-tests')
    db.session.add(t3)
    db.session.commit()
    teach, lee, ray, sam = login(app, 'teach'), login(app, 'lee'), login(app, 'ray'), login(app, 'sam')
    r = sam.post('/messages/reply', data={'body': 'To two', 'to': [str(ids('teach')), str(ids('lee'))], 'to_checked': '1'},
                 headers=FETCH)
    assert r.get_json() == {'ok': True}
    two = Message.query.filter_by(body='To two').one()
    assert not two.to_all and sorted(t.username for t in two.recipients) == ['lee', 'teach']
    assert 'To two' in teach.get('/messages/panel').data.decode() and 'To two' in lee.get('/messages/panel').data.decode()
    assert 'To two' not in ray.get('/messages/panel').data.decode()
    assert 'to you and lee only' in teach.get('/messages/panel').data.decode()
    assert 'to lee, teach only' in sam.get('/messages/panel').data.decode() or 'to teach, lee only' in sam.get('/messages/panel').data.decode()
    # every teacher checked: an ordinary message to all of them
    sam.post('/messages/reply', data={'body': 'To all three', 'to': [str(ids(n)) for n in ('teach', 'lee', 'ray')],
                                      'to_checked': '1'}, headers=FETCH)
    assert Message.query.filter_by(body='To all three').one().to_all
    # none checked: refused, nothing sent
    r = sam.post('/messages/reply', data={'body': 'To nobody', 'to_checked': '1'}, headers=FETCH)
    assert r.status_code == 400 and 'Check at least one teacher' in r.get_json()['error']
    assert not Message.query.filter_by(body='To nobody').count()
    # the app API takes a list too
    from app.api.models import ApiToken
    token = {'Authorization': 'Bearer ' + ApiToken.issue(User.query.filter_by(username='sam').one(), 't')[1]}
    r = app.test_client().post('/api/v2/my/messages', headers=token, json={'body': 'API two', 'to': [ids('lee'), ids('ray')]})
    assert r.status_code == 201
    assert sorted(t.username for t in Message.query.filter_by(body='API two').one().recipients) == ['lee', 'ray']
