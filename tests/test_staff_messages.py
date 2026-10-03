"""Teachers write to other teachers: all of them or chosen ones; students never see any of it."""
from test_flow import app_db, login  # noqa: F401  (fixture)
from test_archive import ids

FETCH = {'X-Requested-With': 'fetch'}


def teachers(db, *names):
    from app.user.models import User
    for name in names:
        t = User(username=name, is_admin=True)
        t.set_password('pw-for-tests')
        db.session.add(t)
    db.session.commit()


def send(c, body, to=None, **extra):
    data = dict({'body': body, 'to_checked': '1'}, **extra)
    if to is not None:
        data['to'] = [str(ids(n)) for n in to] if isinstance(to, (list, tuple)) else to
    return c.post('/messages/teachers/send', data=data, headers=FETCH)


def test_all_teachers_or_chosen_ones(app_db):
    app, db = app_db
    from app.messages.models import StaffMessage
    teachers(db, 'lee', 'ray')
    teach, lee, ray, sam = login(app, 'teach'), login(app, 'lee'), login(app, 'ray'), login(app, 'sam')
    # the picker offers every teacher, like every student
    panel = teach.get('/messages/panel').data.decode()
    assert 'All messages (every student)' in panel and '<option value="teachers">All messages (every teacher)</option>' in panel
    assert 'value="t{}"'.format(ids('lee')) in panel and 'value="t{}"'.format(ids('teach')) not in panel  # not yourself
    # to every teacher: all checked in the "every teacher" view
    view = teach.get('/messages/panel?student=teachers').data.decode()
    assert view.count('name="to" value=') == 2 and view.count('" checked>') == 2 and 'Students never see' in view
    assert send(teach, 'Staff meeting at 3', ['lee', 'ray']).get_json() == {'ok': True}
    everyone = StaffMessage.query.filter_by(body='Staff meeting at 3').one()
    assert everyone.to_all  # every other teacher checked = all of them
    # to one: only they see it
    assert send(teach, 'Can you cover my class?', ['lee']).get_json() == {'ok': True}
    private = StaffMessage.query.filter_by(body='Can you cover my class?').one()
    assert not private.to_all and [t.username for t in private.recipients] == ['lee']
    # counted, popped up, shown
    poll = lee.get('/messages/poll').get_json()
    assert poll['unread'] == 2 and poll['message_preview']['from'] == 'teach'
    assert poll['message_preview']['view'] == 't{}'.format(ids('teach'))
    assert ray.get('/messages/poll').get_json()['unread'] == 1
    lee_view = lee.get('/messages/panel?student=teachers').data.decode()
    assert 'Staff meeting at 3' in lee_view and 'Can you cover my class?' in lee_view and 'to you only' in lee_view
    assert lee.get('/messages/poll').get_json()['unread'] == 0  # seen now
    ray_view = ray.get('/messages/panel?student=teachers').data.decode()
    assert 'Staff meeting at 3' in ray_view and 'Can you cover my class?' not in ray_view
    # one teacher's conversation: just between the two of them
    with_teach = lee.get('/messages/panel?student=t{}'.format(ids('teach'))).data.decode()
    assert 'Can you cover my class?' in with_teach and 'Staff meeting at 3' in with_teach
    assert 'name="to" value="{}" checked'.format(ids('teach')) in with_teach  # writing back to teach only
    assert 'Can you cover my class?' not in ray.get('/messages/panel?student=t{}'.format(ids('teach'))).data.decode()
    # the sender's own message is never "new" for them
    assert teach.get('/messages/poll').get_json()['unread'] == 0
    # none checked: refused
    r = send(teach, 'To nobody', [])
    assert r.status_code == 400 and 'Check at least one teacher' in r.get_json()['error']
    assert not StaffMessage.query.filter_by(body='To nobody').count()
    # students: can't reach any of it, and never see it
    assert sam.post('/messages/teachers/send', data={'body': 'hi', 'to': 'all'}).status_code == 302
    assert StaffMessage.query.count() == 2
    assert sam.get('/messages/teachers').status_code == 302
    for url in ('/messages/panel', '/messages/panel?student=teachers', '/messages/panel?student=t{}'.format(ids('teach')), '/mypage'):
        page = sam.get(url).data.decode()
        assert 'Staff meeting' not in page and 'cover my class' not in page, url
    assert sam.get('/messages/poll').get_json()['unread'] == 0
    # a student id isn't a teacher
    r = teach.post('/messages/teachers/send', data={'body': 'x', 'to': [str(ids('sam'))], 'to_checked': '1'}, headers=FETCH)
    assert r.status_code == 400


def test_the_teachers_page_deleting_and_the_pop_up(app_db):
    app, db = app_db
    from app.messages.models import StaffMessage
    teachers(db, 'lee')
    teach, lee = login(app, 'teach'), login(app, 'lee')
    assert 'Messages between teachers' in teach.get('/messages').data.decode()
    # the page writes with a plain form (one other teacher: no checkboxes, it's to all of them)
    page = teach.get('/messages/teachers').data.decode()
    assert 'All messages (every teacher)' in page and 'name="to" value="all"' in page
    r = teach.post('/messages/teachers/send', data={'body': 'Hello lee', 'to': 'all'})
    assert r.status_code == 302
    msg = StaffMessage.query.one()
    assert msg.to_all and 'Hello lee' in lee.get('/messages/teachers?with={}'.format(ids('teach'))).data.decode()
    # only the writer can delete it
    assert lee.post('/messages/teachers/delete/{}'.format(msg.id), headers=FETCH).status_code == 404
    assert StaffMessage.query.count() == 1
    assert teach.post('/messages/teachers/delete/{}'.format(msg.id), headers=FETCH).get_json() == {'ok': True}
    assert StaffMessage.query.count() == 0
    # an open panel reloads when one arrives (its state changes)
    before = lee.get('/messages/poll').get_json()['messages_state']
    send(teach, 'Another one', 'all')
    assert lee.get('/messages/poll').get_json()['messages_state'] != before
    # the count on the Messages button includes them, until they're seen
    from app.messages.models import unread_messages_for_teacher
    from app.user.models import User
    lee_id = User.query.filter_by(username='lee').one().id
    assert unread_messages_for_teacher(lee_id) == 1 and lee.get('/messages/poll').get_json()['unread'] == 1
    lee.get('/messages/teachers')  # the page shows it: seen
    assert unread_messages_for_teacher(lee_id) == 0
