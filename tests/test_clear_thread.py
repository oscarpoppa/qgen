"""'Clear all' in Messages: takes the conversation shown out of your own view only; everyone
else still sees it, pinned messages stay, and the same conversation comes back empty."""
from test_flow import app_db, login  # noqa: F401  (fixture)
from test_archive import ids
from test_staff_messages import teachers, send as send_staff, FETCH


def clear(c, view):
    return c.post('/messages/clear', data={'view': str(view)}, headers=FETCH)


def test_a_teacher_clears_one_students_conversation_for_themselves_only(app_db):
    app, db = app_db
    teachers(db, 'lee')
    teach, lee, sam, kim = login(app, 'teach'), login(app, 'lee'), login(app, 'sam'), login(app, 'kim')
    teach.post('/messages/send', data={'to': str(ids('sam')), 'body': 'Hi Sam'})
    teach.post('/messages/send', data={'to': str(ids('kim')), 'body': 'Hi Kim'})
    teach.post('/messages/send', data={'to': 'all', 'body': 'Pinned note', 'pin': '1'})
    sam.post('/messages/reply', data={'body': 'Hello teachers'})
    panel = teach.get('/messages/panel?student={}'.format(ids('sam'))).data.decode()
    assert 'Hi Sam' in panel and 'Hello teachers' in panel and 'thread-clear-all' in panel
    assert clear(teach, ids('sam')).get_json() == {'ok': True, 'cleared': 2}
    # the same conversation, now empty for this teacher; the pinned one stays
    panel = teach.get('/messages/panel?student={}'.format(ids('sam'))).data.decode()
    assert 'Hi Sam' not in panel and 'Hello teachers' not in panel and 'Pinned note' in panel
    assert 'Hi Sam' not in teach.get('/messages/{}'.format(ids('sam'))).data.decode()
    # another student's conversation is untouched, and so is everyone else's view
    assert 'Hi Kim' in teach.get('/messages/panel?student={}'.format(ids('kim'))).data.decode()
    assert 'Hello teachers' in lee.get('/messages/panel?student={}'.format(ids('sam'))).data.decode()
    assert 'Hi Sam' in sam.get('/messages/panel').data.decode()
    assert 'Hi Kim' in kim.get('/messages/panel').data.decode()
    # a new message shows as usual
    sam.post('/messages/reply', data={'body': 'One more thing'})
    assert 'One more thing' in teach.get('/messages/panel?student={}'.format(ids('sam'))).data.decode()
    # nothing left to clear: the button is grayed, and clearing again does nothing
    clear(teach, ids('sam'))
    assert clear(teach, ids('sam')).get_json()['cleared'] == 0
    assert 'disabled title="There\'s nothing to clear here."' in teach.get('/messages/panel?student={}'.format(ids('sam'))).data.decode()


def test_clearing_all_messages_counts_them_read(app_db):
    app, db = app_db
    teach, sam, kim = login(app, 'teach'), login(app, 'sam'), login(app, 'kim')
    sam.post('/messages/reply', data={'body': 'From Sam'})
    kim.post('/messages/reply', data={'body': 'From Kim'})
    assert teach.get('/messages/poll').get_json()['unread'] == 2
    state = teach.get('/messages/poll').get_json()['messages_state']
    assert clear(teach, 'all').get_json()['cleared'] == 2
    assert teach.get('/messages/poll').get_json()['unread'] == 0
    # other open pages see the change
    assert teach.get('/messages/poll').get_json()['messages_state'] != state
    panel = teach.get('/messages/panel?student=all').data.decode()
    assert 'From Sam' not in panel and 'From Kim' not in panel
    # the Messages page's list doesn't show the cleared message either
    assert 'From Sam' not in teach.get('/messages').data.decode()


def test_a_student_clears_their_view(app_db):
    app, db = app_db
    teachers(db, 'lee')
    teach, lee, sam = login(app, 'teach'), login(app, 'lee'), login(app, 'sam')
    teach.post('/messages/send', data={'to': str(ids('sam')), 'body': 'From teach'})
    lee.post('/messages/send', data={'to': str(ids('sam')), 'body': 'From lee'})
    teach.post('/messages/send', data={'to': str(ids('sam')), 'body': 'Stays pinned', 'pin': '1'})
    sam.post('/messages/reply', data={'body': 'My question'})
    assert sam.get('/messages/poll').get_json()['unread'] == 3
    # just the conversation with one teacher
    # (what Sam sent to all the teachers is part of that conversation too)
    assert clear(sam, ids('lee')).get_json()['cleared'] == 2
    panel = sam.get('/messages/panel?student=all').data.decode()
    assert 'From lee' not in panel and 'My question' not in panel and 'From teach' in panel
    # then everything: the pinned message stays, cleared ones count as read
    clear(sam, 'all')
    panel = sam.get('/messages/panel?student=all').data.decode()
    assert 'From teach' not in panel and 'Stays pinned' in panel
    assert sam.get('/messages/poll').get_json()['unread'] == 0
    # the teachers still see all of it
    convo = teach.get('/messages/{}'.format(ids('sam'))).data.decode()
    assert 'From teach' in convo and 'My question' in convo
    # a student can't clear for a student, or as a teacher
    assert clear(sam, ids('kim')).status_code == 404


def test_teachers_clear_teachers_messages_for_themselves(app_db):
    app, db = app_db
    teachers(db, 'lee', 'ray')
    teach, lee, ray = login(app, 'teach'), login(app, 'lee'), login(app, 'ray')
    send_staff(lee, 'Lee to teach', to=['teach'])
    send_staff(ray, 'Ray to all', to='all')
    assert clear(teach, 't{}'.format(ids('lee'))).get_json()['cleared'] == 1
    panel = teach.get('/messages/panel?student=teachers').data.decode()
    assert 'Lee to teach' not in panel and 'Ray to all' in panel
    clear(teach, 'teachers')
    assert 'Ray to all' not in teach.get('/messages/teachers').data.decode()
    # the others still have theirs
    assert 'Lee to teach' in lee.get('/messages/panel?student=teachers').data.decode()
    assert 'Ray to all' in ray.get('/messages/teachers').data.decode()
    # a student isn't a teacher to clear with
    assert clear(teach, 't{}'.format(ids('sam'))).status_code == 404


def test_the_pages_clear_and_come_back(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    teach.post('/messages/send', data={'to': str(ids('sam')), 'body': 'Hi Sam'})
    page = '/messages/{}'.format(ids('sam'))
    assert 'thread-clear-all' in teach.get(page).data.decode()
    r = teach.post('/messages/clear', data={'view': str(ids('sam'))}, headers={'Referer': 'http://localhost' + page})
    assert r.status_code == 302 and r.headers['Location'].endswith(page)
    assert 'Hi Sam' not in teach.get(page).data.decode()
