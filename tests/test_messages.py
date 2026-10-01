from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)


def test_two_way_messages_announcements_and_notices(app_db):
    app, db = app_db
    from app.user.models import User
    from app.messages.models import Message
    teacher = login(app, 'teach')
    sam_id = User.query.filter_by(username='sam').one().id
    kim_id = User.query.filter_by(username='kim').one().id

    # teacher -> one student
    r = teacher.post('/messages/send', data={'to': str(sam_id), 'body': 'Great <b>work</b> today!'})
    assert r.status_code == 302
    sam = login(app, 'sam')
    assert sam.get('/messages/poll').get_json()['unread'] == 1
    home = sam.get('/messages/panel').data.decode()
    assert 'Great &lt;b&gt;work&lt;/b&gt; today!' in home and 'msg-new' in home  # escaped, and marked new
    assert sam.get('/messages/poll').get_json()['unread'] == 0  # seeing it marks it read

    # kim can't see sam's messages
    kim = login(app, 'kim')
    assert 'Great' not in kim.get('/messages/panel').data.decode()
    assert kim.get('/messages/{}'.format(sam_id)).status_code == 302  # teacher page

    # student replies; teacher sees an unread count, then the conversation
    r = sam.post('/messages/reply', data={'body': 'Thanks! Can I retake quiz 2?'})
    assert r.status_code == 302
    assert teacher.get('/messages/poll').get_json()['unread'] == 1
    inbox = teacher.get('/messages').data.decode()
    assert 'Can I retake quiz 2?' in inbox and 'aria-label="1 unread"' in inbox
    convo = teacher.get('/messages/{}'.format(sam_id)).data.decode()
    assert 'Great &lt;b&gt;work' in convo and 'Can I retake quiz 2?' in convo
    assert teacher.get('/messages/poll').get_json()['unread'] == 0

    # announcement to everyone
    teacher.post('/messages/send', data={'to': 'all', 'body': 'No class Friday.'})
    assert Message.query.filter_by(kind='announcement').count() == 2
    assert 'No class Friday.' in kim.get('/messages/panel').data.decode()

    # empty and overlong messages are refused
    teacher.post('/messages/send', data={'to': str(sam_id), 'body': '   '})
    sam.post('/messages/reply', data={'body': 'x' * 2001})
    assert Message.query.filter(Message.body.in_(['', 'x' * 2001])).count() == 0
    # teachers don't use the student reply box; students can't message each other
    assert teacher.post('/messages/reply', data={'body': 'hi'}).status_code == 404
    assert sam.post('/messages/send', data={'to': str(kim_id), 'body': 'hi'}).status_code == 302
    assert Message.query.filter_by(student_id=kim_id, body='hi').count() == 0

    # automatic notice when a quiz is assigned
    f = problem_form('numeric', 'N', '[a] + 1', 'a + 1', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}])
    teacher.post('/quiz/makevprob', data=f)
    from app.qgen.models import VProblem, VQuiz
    teacher.post('/quiz/makevquiz', data={'title': 'Quiz 9', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id, kim_id]})
    assert Message.query.filter_by(kind='notice', from_teacher=True).count() == 2  # the students' own
    # ...in the notices panel, not the conversation, with its own count
    assert sam.get('/messages/poll').get_json()['notices'] == 1
    assert 'New quiz' not in sam.get('/messages/panel').data.decode()
    assert 'New quiz: &#34;Quiz 9&#34;' in sam.get('/messages/notices').data.decode()
    assert sam.get('/messages/poll').get_json()['notices'] == 0

    # deleting a student removes their conversation
    teacher.post('/deluser/{}'.format(kim_id))
    db.session.expire_all()
    assert Message.query.filter_by(student_id=kim_id).count() == 0


def test_chosen_students_and_pinning_on_the_web(app_db):
    app, db = app_db
    from app.user.models import User
    from app.messages.models import Message
    teacher = login(app, 'teach')
    sam_id = User.query.filter_by(username='sam').one().id
    kim_id = User.query.filter_by(username='kim').one().id
    # to chosen students, pinned
    r = teacher.post('/messages/send', data={'to': 'chosen', 'students': [str(sam_id)], 'body': 'Bring a ruler.', 'pin': '1'})
    assert r.status_code == 302
    m = Message.query.one()
    assert m.pinned and m.student_id == sam_id
    assert teacher.post('/messages/send', data={'to': 'chosen', 'body': 'x'}).status_code == 302
    assert Message.query.count() == 1  # nobody ticked: nothing sent
    # everyone, pinned: one pinned entry for the teacher, one per student
    teacher.post('/messages/send', data={'to': 'all', 'body': 'Test Friday!', 'pin': '1'})
    home = login(app, 'kim').get('/messages/panel').data.decode()
    assert 'pinned-list' in home and 'Test Friday!' in home
    assert teacher.get('/messages').data.decode().count('Unpin') == 2
    batch_msg = Message.query.filter_by(body='Test Friday!').first()
    teacher.post('/messages/pin/{}'.format(batch_msg.id), data={'pinned': '0'})
    assert Message.query.filter_by(body='Test Friday!', pinned=True).count() == 0
    assert 'pinned-list' not in login(app, 'kim').get('/messages/panel').data.decode()
    # a teacher account can't be chosen as a recipient
    teacher.post('/messages/send', data={'to': 'chosen', 'students': [str(sam_id), '1'], 'body': 'y'})
    assert Message.query.filter_by(body='y').count() == 0
    assert kim_id != sam_id


def test_side_panels_on_every_page(app_db):
    app, db = app_db
    from app.user.models import User
    sam_id = User.query.filter_by(username='sam').one().id
    kim_id = User.query.filter_by(username='kim').one().id
    teacher = login(app, 'teach')

    # every page has the two panels and their buttons, for teachers and students
    for client, url in ((teacher, '/mypage'), (teacher, '/quiz/listvp'), (login(app, 'sam'), '/mypage'), (login(app, 'sam'), '/profile')):
        page = client.get(url).data.decode()
        assert 'id="dock-notices"' in page and 'id="dock-messages"' in page and 'data-pane="notices"' in page
    # ...and not before signing in
    assert 'id="dock"' not in app.test_client().get('/login').data.decode()

    # the panel starts on everyone's messages together; a student's id shows one conversation
    box = teacher.get('/messages/panel').data.decode()
    assert 'id="msg-student"' in box and '<option value="all" selected>' in box
    # ...where the send box writes to every student
    assert 'name="to" value="all"' in box and 'Send to all 2 students' in box
    box = teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()
    assert 'reply-box' in box and 'Write to sam' in box and 'data-student="all"' in box

    # students write: the all-messages view shows both, labeled, with Reply buttons, and marks them read
    login(app, 'kim').post('/messages/reply', data={'body': 'Is the quiz timed?'})
    login(app, 'sam').post('/messages/reply', data={'body': 'Can I retake it?'})
    poll = teacher.get('/messages/poll').get_json()
    assert poll['unread'] == 2 and poll['message_preview']['from'] == 'sam'
    box = teacher.get('/messages/panel?student=all').data.decode()
    assert 'Is the quiz timed?' in box and 'Can I retake it?' in box and box.count('msg-new') == 2
    assert 'Reply to kim' in box and 'Reply to sam' in box
    assert box.index('Is the quiz timed?') < box.index('Can I retake it?')  # newest at the bottom
    assert teacher.get('/messages/poll').get_json()['unread'] == 0
    # a teacher's own message in that view says who it went to
    teacher.post('/messages/send', data={'to': str(kim_id), 'body': 'Yes, 20 minutes.'}, headers={'X-Requested-With': 'fetch'})
    assert 'to kim' in teacher.get('/messages/panel').data.decode()
    # one student's conversation shows only that student's messages
    box = teacher.get('/messages/panel?student={}'.format(kim_id)).data.decode()
    assert 'Is the quiz timed?' in box and 'Can I retake it?' not in box
    assert '<option value="{}" selected>'.format(kim_id) in box

    # sending from the panel answers with JSON (the panel reloads itself; no page change, no flash)
    r = teacher.post('/messages/send', data={'to': str(kim_id), 'body': 'No, take your time.'}, headers={'X-Requested-With': 'fetch'})
    assert r.get_json() == {'ok': True, 'sent': 1}
    r = teacher.post('/messages/send', data={'to': str(kim_id), 'body': '  '}, headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 400 and r.get_json()['ok'] is False
    kim = login(app, 'kim')
    assert kim.post('/messages/reply', data={'body': 'Thanks!'}, headers={'X-Requested-With': 'fetch'}).get_json() == {'ok': True}
    assert 'No, take your time.' in kim.get('/messages/panel').data.decode()
    # a plain form still goes to the conversation page
    r = teacher.post('/messages/send', data={'to': str(kim_id), 'body': 'Good luck!'})
    assert r.headers['Location'].endswith('/messages/{}'.format(kim_id))

    # choosing another student; a teacher's id (or nonsense) falls back to a student
    assert '<option value="{}" selected>'.format(sam_id) in teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()
    teach_id = User.query.filter_by(username='teach').one().id
    assert '<option value="{}" selected>'.format(teach_id) not in teacher.get('/messages/panel?student={}'.format(teach_id)).data.decode()
    assert teacher.get('/messages/panel?student=abc').status_code == 200

    # the poll's newest id changes when any student writes, so an open panel can reload
    before = teacher.get('/messages/poll').get_json()['latest']
    login(app, 'sam').post('/messages/reply', data={'body': 'Me too?'})
    assert teacher.get('/messages/poll').get_json()['latest'] > before

    # students get their own panel, never the teacher's
    box = login(app, 'sam').get('/messages/panel').data.decode()
    assert 'id="messages"' in box and 'id="msg-student"' not in box and 'Write to your teacher' in box


def test_teachers_get_notices_apart_from_messages(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    sam_id = User.query.filter_by(username='sam').one().id
    teacher = login(app, 'teach')
    f = problem_form('numeric', 'N', '[a] + 1', 'a + 1', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}])
    teacher.post('/quiz/makevprob', data=f)
    teacher.post('/quiz/makevquiz', data={'title': 'Quiz 5', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    assert 'teach assigned &#34;Quiz 5&#34;' in teacher.get('/messages/notices').data.decode()  # read it

    # sam hands in: the teachers get a notice, not a message
    from app.qgen import services as S
    with app.test_request_context():
        S.submit(cq, {1: '5'})
    poll = teacher.get('/messages/poll').get_json()
    assert poll['notices'] == 1 and poll['unread'] == 0
    assert poll['notice_preview']['from'] is None and 'sam handed in "Quiz 5"' in poll['notice_preview']['text']
    panel = teacher.get('/messages/notices').data.decode()
    assert 'sam handed in &#34;Quiz 5&#34;' in panel and 'notice-new' in panel
    # its Open goes to that attempt's results, which a teacher can see
    from app.messages.models import Message
    link = Message.query.filter(Message.body.like('sam handed in%')).one().link
    assert link == '/quiz/take/{}'.format(cq.id)
    assert 'Quiz 5' in teacher.get(link).data.decode()
    assert teacher.get('/messages/poll').get_json()['notices'] == 0
    # not in the conversation or inbox, and never shown to the student
    assert 'handed in' not in teacher.get('/messages/{}'.format(sam_id)).data.decode()
    assert 'handed in' not in teacher.get('/messages').data.decode()
    sam = login(app, 'sam')
    assert 'handed in' not in sam.get('/messages/notices').data.decode()
    assert 'handed in' not in sam.get('/messages/panel').data.decode()
    # ...nor through the API (whose student messages come from thread())
    from app.messages import services as M
    assert all('handed in' not in m.body for m in M.thread(sam_id))

    # a new student signing up is a notice for the teachers too
    from app.qgen.models import Setting
    Setting.put('class_code', 'maple-7')
    app.test_client().post('/register', data={'class_code': 'maple-7', 'username': 'dee', 'email': '',
                                             'password': 'pw-for-tests', 'retype_password': 'pw-for-tests'})
    assert User.query.filter_by(username='dee').count() == 1
    assert 'New student signed up: dee.' in teacher.get('/messages/notices').data.decode()


def test_message_actions_need_the_page_token(app_db):
    # another website can't make a signed-in browser send or pin messages
    app, db = app_db
    from app.user.models import User
    from app.messages.models import Message
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        teacher.post('/messages/send', data={'to': str(sam_id), 'body': 'forged', 'csrf_token': 'nope'})
        sam.post('/messages/reply', data={'body': 'forged too'})
        assert Message.query.filter(Message.body.in_(['forged', 'forged too'])).count() == 0
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_conversation_page_switches_students(app_db):
    app, db = app_db
    from app.user.models import User
    sam_id = User.query.filter_by(username='sam').one().id
    kim_id = User.query.filter_by(username='kim').one().id
    teacher = login(app, 'teach')
    login(app, 'kim').post('/messages/reply', data={'body': 'Hello from kim'})
    page = teacher.get('/messages/{}'.format(sam_id)).data.decode()
    # only sam's thread on sam's page, and a menu of every student to switch to
    assert 'Hello from kim' not in page and 'id="switch-student"' in page
    assert '<option value="/messages/{}" selected>sam</option>'.format(sam_id) in page
    assert '<option value="/messages/{}">kim (1 new)</option>'.format(kim_id) in page
    assert 'Hello from kim' in teacher.get('/messages/{}'.format(kim_id)).data.decode()


def test_new_from_others_button_goes_to_them(app_db):
    app, db = app_db
    from app.user.models import User
    sam_id = User.query.filter_by(username='sam').one().id
    kim_id = User.query.filter_by(username='kim').one().id
    teacher = login(app, 'teach')
    box = teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()
    assert 'new from' not in box  # nothing waiting
    # one other student wrote: the button names them and opens their conversation
    login(app, 'kim').post('/messages/reply', data={'body': 'Hi'})
    login(app, 'kim').post('/messages/reply', data={'body': 'Still there?'})
    box = teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()
    assert 'class="badge badge-warn badge-btn show-student" data-student="{}"'.format(kim_id) in box
    assert '2 new from kim →' in box
    # several students: it opens all messages instead
    from app.messages import services as M
    M.reply(User.query.filter_by(username='sam').one(), 'Me too')
    box = teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()  # reading sam's clears sam's
    assert '2 new from kim →' in box
    extra = User(username='lee'); extra.set_password('pw-for-tests'); db.session.add(extra); db.session.commit()
    M.reply(extra, 'Hello from lee')
    box = teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()
    assert 'data-student="all"' in box and '3 new from 2 students →' in box


def test_teachers_get_a_notice_when_a_quiz_is_assigned(app_db):
    app, db = app_db
    from datetime import datetime, timedelta
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz
    from app.messages.models import Message
    sam_id = User.query.filter_by(username='sam').one().id
    kim_id = User.query.filter_by(username='kim').one().id
    teacher = login(app, 'teach')
    f = problem_form('numeric', 'N', '[a] + 1', 'a + 1', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}])
    teacher.post('/quiz/makevprob', data=f)
    teacher.post('/quiz/makevquiz', data={'title': 'Quiz 7', 'vplist': str(VProblem.query.one().id)})
    due = (datetime.now() + timedelta(days=3)).replace(hour=17, minute=0, second=0, microsecond=0)
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id, kim_id],
                                       'closes_at': due.strftime('%Y-%m-%dT%H:%M'), 'time_limit': '20'})
    # one notice for the whole assignment, on the assigning teacher's record, for the teachers only
    notices = Message.query.filter_by(kind='notice', from_teacher=False).all()
    assert len(notices) == 1
    body = notices[0].body
    assert body.startswith('teach assigned "Quiz 7" to 2 students: ') and 'sam' in body and 'kim' in body
    assert 'Due {}'.format(due.strftime('%b %d at %I:%M %p')) in body and '20 minute time limit.' in body
    assert notices[0].student_id == User.query.filter_by(username='teach').one().id
    # "Open" goes to the quiz that was assigned, and that page shows it
    assert notices[0].link == '/quiz/listvq/{}'.format(VQuiz.query.one().id)
    assert 'Quiz 7' in teacher.get(notices[0].link).data.decode()
    assert teacher.get('/messages/poll').get_json()['notices'] == 1
    assert 'teach assigned &#34;Quiz 7&#34;' in teacher.get('/messages/notices').data.decode()
    # students still get their own "New quiz" notice, and never see the teachers' one
    sam = login(app, 'sam')
    page = sam.get('/messages/notices').data.decode()
    assert 'New quiz: &#34;Quiz 7&#34;' in page and 'assigned' not in page
    # the API's assign does the same
    from test_api import Api
    Api(app, 'teach').post('/quizzes/{}/assign'.format(VQuiz.query.one().id), json={'students': [sam_id]})
    assert Message.query.filter(Message.kind == 'notice', Message.from_teacher.is_(False),
                                Message.body.like('teach assigned "Quiz 7" to 1 student: sam.%')).count() == 1


def test_deleting_messages(app_db):
    app, db = app_db
    from app.user.models import User
    from app.messages.models import Message
    sam_id = User.query.filter_by(username='sam').one().id
    kim_id = User.query.filter_by(username='kim').one().id
    teacher, sam, kim = login(app, 'teach'), login(app, 'sam'), login(app, 'kim')
    J = {'X-Requested-With': 'fetch'}
    teacher.post('/messages/send', data={'to': str(sam_id), 'body': 'From the teacher'})
    sam.post('/messages/reply', data={'body': 'Mine to delete'})
    sam.post('/messages/reply', data={'body': 'Teacher deletes this'})
    kim.post('/messages/reply', data={'body': 'Kim wrote this'})
    mid = lambda body: Message.query.filter_by(body=body).one().id

    # students: Delete on everything in their own conversation, nothing in anyone else's
    box = sam.get('/messages/panel').data.decode()
    assert box.count('aria-label="Delete this message"') == 3
    assert 'Your teacher will still have it' in box  # the teacher's message: removed from sam's view only
    assert sam.post('/messages/delete/{}'.format(mid('Kim wrote this')), headers=J).status_code == 403
    teacher_msg = mid('From the teacher')
    assert sam.post('/messages/delete/{}'.format(teacher_msg), headers=J).get_json() == {'ok': True, 'deleted': 1}
    assert 'From the teacher' not in sam.get('/messages/panel').data.decode()
    assert db.session.get(Message, teacher_msg) is not None  # still there for the teacher...
    box = teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()
    assert 'From the teacher' in box and 'sam removed this from their messages' in box  # ...marked
    from app.messages import services as MS
    assert all(m.body != 'From the teacher' for m in MS.thread(sam_id))  # and not through the API
    assert sam.post('/messages/delete/{}'.format(mid('Mine to delete')), headers=J).get_json() == {'ok': True, 'deleted': 1}
    assert Message.query.filter_by(body='Mine to delete').count() == 0
    # teachers: any message, from the panel (JSON) or the conversation page (redirect)
    assert 'Delete this message' in teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()
    assert teacher.post('/messages/delete/{}'.format(mid('Teacher deletes this')), headers=J).get_json()['ok']
    r = teacher.post('/messages/delete/{}'.format(teacher_msg))  # the teacher deletes it for good
    assert r.status_code == 302
    assert Message.query.filter(Message.body.in_(['Teacher deletes this', 'From the teacher'])).count() == 0
    assert teacher.post('/messages/delete/999999', headers=J).status_code == 404

    # an announcement to several: "only from this student" or "from every student who got it"
    teacher.post('/messages/send', data={'to': 'all', 'body': 'Test Friday', 'pin': '1'})
    box = teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()
    assert 'Only from sam' in box and 'From every student who got it' in box
    first = Message.query.filter_by(body='Test Friday', student_id=sam_id).one().id
    teacher.post('/messages/delete/{}'.format(first), headers=J)
    assert Message.query.filter_by(body='Test Friday').count() == 1  # kim keeps hers
    teacher.post('/messages/delete/{}'.format(Message.query.filter_by(body='Test Friday').one().id), data={'everyone': '1'}, headers=J)
    teacher.post('/messages/send', data={'to': 'all', 'body': 'Quiz moved'})
    one = Message.query.filter_by(body='Quiz moved', student_id=kim_id).one().id
    assert teacher.post('/messages/delete/{}'.format(one), data={'everyone': '1'}, headers=J).get_json()['deleted'] == 2
    assert Message.query.filter(Message.body.in_(['Test Friday', 'Quiz moved'])).count() == 0
    # a student can't use "everyone" to touch other students' copies: it only leaves sam's view
    teacher.post('/messages/send', data={'to': 'all', 'body': 'Hands off'})
    assert sam.post('/messages/delete/{}'.format(Message.query.filter_by(body='Hands off', student_id=sam_id).one().id),
                    data={'everyone': '1'}, headers=J).get_json()['deleted'] == 1
    assert Message.query.filter_by(body='Hands off').count() == 2
    assert Message.query.filter_by(body='Hands off', hidden_for_student=True).one().student_id == sam_id
    assert 'Hands off' in login(app, 'kim').get('/messages/panel').data.decode()
    # notices aren't deleted this way
    from app.messages.models import notify
    n = notify(sam_id, 'New quiz: "X".'); db.session.commit()
    assert teacher.post('/messages/delete/{}'.format(n.id), headers=J).status_code == 403


def test_clearing_notices(app_db):
    app, db = app_db
    from app.user.models import User
    from app.messages.models import Message, notify, notify_teachers
    sam_id = User.query.filter_by(username='sam').one().id
    kim_id = User.query.filter_by(username='kim').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    J = {'X-Requested-With': 'fetch'}
    a = notify(sam_id, 'New quiz: "A".'); b = notify(sam_id, 'New quiz: "B".'); k = notify(kim_id, 'New quiz: "K".')
    t = notify_teachers(sam_id, 'sam handed in "A": 90%.')
    db.session.commit()
    page = sam.get('/messages/notices').data.decode()
    assert page.count('aria-label="Clear this notice"') == 2 and 'Clear all' in page
    # each person clears only their own notices
    assert sam.post('/messages/notices/clear/{}'.format(k.id), headers=J).status_code == 404
    assert sam.post('/messages/notices/clear/{}'.format(t.id), headers=J).status_code == 404
    assert sam.post('/messages/notices/clear/{}'.format(a.id), headers=J).get_json() == {'ok': True, 'cleared': 1}
    assert sam.post('/messages/notices/clear', headers=J).get_json() == {'ok': True, 'cleared': 1}  # "Clear all"
    assert Message.query.filter(Message.id.in_([a.id, b.id])).count() == 0
    assert db.session.get(Message, k.id) is not None and db.session.get(Message, t.id) is not None
    # teachers clear teachers' notices, never students'
    assert teacher.post('/messages/notices/clear', headers=J).get_json()['cleared'] == 1
    assert db.session.get(Message, k.id) is not None


def test_delete_and_clear_need_the_page_token(app_db):
    app, db = app_db
    from app.user.models import User
    from app.messages.models import Message, notify
    sam_id = User.query.filter_by(username='sam').one().id
    sam = login(app, 'sam')
    sam.post('/messages/reply', data={'body': 'keep me'})
    n = notify(sam_id, 'New quiz: "Z".'); db.session.commit()
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        sam.post('/messages/delete/{}'.format(Message.query.filter_by(body='keep me').one().id))
        sam.post('/messages/notices/clear')
        assert Message.query.filter_by(body='keep me').count() == 1 and db.session.get(Message, n.id) is not None
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_student_pages_refresh_when_graded(app_db):
    # an open "My quizzes" or "waiting for grading" page reloads when a notice arrives
    # (e.g. "graded"), so its labels don't go stale; a quiz being taken never does
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    teacher.post('/quiz/makevprob', data=problem_form('essay', 'Why', 'Explain why.', '', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Essay 1', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    flag = 'data-refresh-on-notice'
    assert flag not in sam.get('/quiz/take/{}'.format(cq.id)).data.decode()  # taking it: never reload
    with app.test_request_context():
        S.submit(cq, {1: 'Because.'})
    waiting = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert flag in waiting
    home = sam.get('/mypage').data.decode()
    assert flag in home and 'Being graded' in home
    assert flag not in teacher.get('/mypage').data.decode()
    # graded: the notice the page is waiting for arrives, and the reloaded page shows the result
    before = sam.get('/messages/poll').get_json()['latest_notice']
    with app.test_request_context():
        S.grade_essays(cq, {cq.cproblems[0].id: {'credit': 80}}, finish=True)
    assert sam.get('/messages/poll').get_json()['latest_notice'] != before
    home = sam.get('/mypage').data.decode()
    assert 'Being graded' not in home and '80%' in home


def test_results_page_refreshes_when_answers_are_released(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    f = problem_form('numeric', 'N', '[a] + 1', 'a + 1', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}])
    teacher.post('/quiz/makevprob', data=f)
    teacher.post('/quiz/makevquiz', data={'title': 'Hidden', 'vplist': str(VProblem.query.one().id), 'hide_answers': 'y'})
    vq = VQuiz.query.one()
    assert vq.hide_answers
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    with app.test_request_context():
        S.submit(cq, {1: '999'})  # wrong
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'data-refresh-on-notice' in page and '<dt>Correct answer</dt>' not in page
    teacher.post('/quiz/releasevq/{}'.format(vq.id))
    db.session.expire_all()
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert '<dt>Correct answer</dt>' in page and 'data-refresh-on-notice' not in page
    assert 'correct answers for &#34;Hidden&#34;' in sam.get('/messages/notices').data.decode()


def test_questions_are_asked_in_the_page_and_delete_is_always_an_x(app_db):
    # browsers can switch their own confirm() pop-ups off, after which buttons that
    # use them silently do nothing; every "are you sure?" is asked inside the page
    import glob, os, re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in glob.glob(os.path.join(root, 'app', '**', '*.html'), recursive=True) + glob.glob(os.path.join(root, 'static', 'js', '*.js')):
        text = open(path).read()
        if path.endswith('confirm.js'):
            continue
        assert not re.search(r'(?<![\w.])confirm\(', text), path  # only window.confirm as a fallback
        assert 'onsubmit="return confirm' not in text, path
    app, db = app_db
    from app.user.models import User
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    teacher.post('/messages/send', data={'to': str(sam_id), 'body': 'Hello'})
    teacher.post('/messages/send', data={'to': 'all', 'body': 'Everyone hello'})
    sam.post('/messages/reply', data={'body': 'Hi'})
    for client, url in ((sam, '/messages/panel'), (teacher, '/messages/panel?student={}'.format(sam_id)),
                        (teacher, '/messages/panel?student=all'), (teacher, '/messages/{}'.format(sam_id))):
        page = client.get(url).data.decode()
        assert 'class="msg-x"' in page and '>Delete<' not in page and 'Delete</button>' not in page, url
        # each question names its button
        assert all('data-confirm-ok=' in f for f in re.findall(r'<form[^>]*data-confirm=[^>]*>', page)), url
    assert 'js/confirm.js' in sam.get('/mypage').data.decode()



def test_send_to_all_students_from_the_panel(app_db):
    app, db = app_db
    from app.messages.models import Message
    teacher = login(app, 'teach')
    J = {'X-Requested-With': 'fetch'}
    r = teacher.post('/messages/send', data={'to': 'all', 'body': 'Quiz Friday'}, headers=J)
    assert r.get_json() == {'ok': True, 'sent': 2}
    r = teacher.post('/messages/send', data={'to': 'all', 'body': 'Bring pencils', 'pin': '1'}, headers=J)
    assert r.get_json()['sent'] == 2
    assert Message.query.filter_by(body='Quiz Friday', pinned=False).count() == 2
    assert Message.query.filter_by(body='Bring pencils', pinned=True).count() == 2
    for name in ('sam', 'kim'):
        page = login(app, name).get('/messages/panel').data.decode()
        assert 'Quiz Friday' in page and 'pinned-list' in page and 'Bring pencils' in page


def test_sending_to_everyone_asks_first(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    panel = teacher.get('/messages/panel?student=all').data.decode()
    assert 'data-confirm="Are you sure you want to send this to all 2 students?"' in panel
    assert 'data-confirm-ok="Send to everyone"' in panel
    page = teacher.get('/messages').data.decode()
    assert 'data-confirm="Are you sure you want to send this to all 2 students?"' in page
    # one student's conversation doesn't ask
    from app.user.models import User
    sam_id = User.query.filter_by(username='sam').one().id
    assert 'send this to all' not in teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()


def test_pins_and_deletions_reach_open_panels(app_db):
    # the poll's "state" changes whenever a panel's contents change, not only when
    # something new arrives, so open panels reload on every screen
    app, db = app_db
    from app.user.models import User
    from app.messages.models import Message
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam, kim = login(app, 'teach'), login(app, 'sam'), login(app, 'kim')
    J = {'X-Requested-With': 'fetch'}
    teacher.post('/messages/send', data={'to': str(sam_id), 'body': 'Pin me'})
    state = lambda c: c.get('/messages/poll').get_json()['messages_state']
    s0, t0, k0 = state(sam), state(teacher), state(kim)
    mid = Message.query.filter_by(body='Pin me').one().id
    teacher.post('/messages/pin/{}'.format(mid), data={'pinned': '1'}, headers=J)
    s1 = state(sam)
    assert s1 != s0 and state(teacher) != t0 and state(kim) == k0  # kim's panel isn't affected
    assert sam.get('/messages/poll').get_json()['latest'] == mid  # nothing new arrived...
    teacher.post('/messages/pin/{}'.format(mid), data={'pinned': '0'}, headers=J)
    assert state(sam) != s1  # ...but unpinning shows too
    s2 = state(sam)
    sam.post('/messages/delete/{}'.format(mid), headers=J)  # sam removes it from their view
    assert state(sam) != s2
    t2 = state(teacher)
    teacher.post('/messages/delete/{}'.format(mid), headers=J)  # deleted for good
    assert state(teacher) != t2
    # notices: clearing one changes the Notices panel's state
    from app.messages.models import notify
    notify(sam_id, 'New quiz: "Z".'); db.session.commit()
    n0 = sam.get('/messages/poll').get_json()['notices_state']
    sam.post('/messages/notices/clear', headers=J)
    assert sam.get('/messages/poll').get_json()['notices_state'] != n0


def test_all_messages_view_shows_an_announcement_once(app_db):
    app, db = app_db
    from app.messages.models import Message
    teacher = login(app, 'teach')
    J = {'X-Requested-With': 'fetch'}
    teacher.post('/messages/send', data={'to': 'all', 'body': 'No class Monday'}, headers=J)
    box = teacher.get('/messages/panel?student=all').data.decode()
    assert box.count('No class Monday') == 1 and 'to all 2 students' in box
    assert 'Delete this announcement for all 2 students who got it?' in box
    first = Message.query.filter_by(body='No class Monday').order_by(Message.id).first().id
    assert teacher.post('/messages/delete/{}'.format(first), data={'everyone': '1'}, headers=J).get_json()['deleted'] == 2
    # in one student's conversation it's still that student's copy, with both choices
    teacher.post('/messages/send', data={'to': 'all', 'body': 'Quiz moved'}, headers=J)
    from app.user.models import User
    sam_id = User.query.filter_by(username='sam').one().id
    box = teacher.get('/messages/panel?student={}'.format(sam_id)).data.decode()
    assert 'Only from sam' in box and 'From every student who got it' in box and 'to all 2 students' not in box


def test_teachers_get_a_notice_when_a_retake_is_given(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    from app.messages.models import Message
    sam_id = User.query.filter_by(username='sam').one().id
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Again', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    with app.test_request_context():
        S.submit(cq, {1: '5'})
    teacher.get('/messages/notices')  # read what's there so far
    # the Retake button: a notice for the teachers, and still one for the student
    assert teacher.post('/quiz/retcq/{}'.format(cq.id)).status_code == 302
    poll = teacher.get('/messages/poll').get_json()
    assert poll['notices'] == 1 and poll['notice_preview']['text'] == 'teach gave sam a retake of "Again".'
    notice = Message.query.filter_by(body='teach gave sam a retake of "Again".').one()
    assert not notice.from_teacher and notice.link == '/quiz/listuser/{}'.format(sam_id)
    page = login(app, 'sam').get('/messages/notices').data.decode()
    assert 'You can try &#34;Again&#34; again.' in page and 'gave sam a retake' not in page
    # through the API too
    from test_api import Api
    new = CQuiz.query.filter_by(assignee=sam_id).order_by(CQuiz.id.desc()).first()
    with app.test_request_context():
        S.submit(new, {1: '4'})
    Api(app, 'teach').post('/attempts/{}/retake'.format(new.id))
    assert Message.query.filter_by(body='teach gave sam a retake of "Again".').count() == 2


def test_review_count_next_to_review_stays_current(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher = login(app, 'teach')
    page = teacher.get('/quiz/listvp').data.decode()
    assert page.count('class="count nav-review"') == 2 and 'nav-review" aria-label="0 waiting" hidden' in page
    assert teacher.get('/messages/poll').get_json()['review'] == 0
    teacher.post('/quiz/makevprob', data=problem_form('essay', 'Why', 'Explain.', '', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Essay', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    with app.test_request_context():
        S.submit(cq, {1: 'Because.'})
    # the poll tells open pages; a fresh page shows it next to Review and on the Menu button
    assert teacher.get('/messages/poll').get_json()['review'] == 1
    page = teacher.get('/quiz/listvp').data.decode()
    assert page.count('aria-label="1 waiting" >1</span>') + page.count('aria-label="1 waiting for grading" >1</span>') == 2
    # students' polls don't carry it, and their pages don't show it
    sam = login(app, 'sam')
    assert sam.get('/messages/poll').get_json()['review'] is None
    assert 'nav-review' not in sam.get('/mypage').data.decode()
