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
    assert Message.query.filter_by(kind='notice').count() == 2
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
    assert 'id="msg-student"' in box and '<option value="all" selected>' in box and 'reply-box' not in box
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
    assert r.get_json() == {'ok': True}
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

    # sam hands in: the teachers get a notice, not a message
    from app.qgen import services as S
    with app.test_request_context():
        S.submit(cq, {1: '5'})
    poll = teacher.get('/messages/poll').get_json()
    assert poll['notices'] == 1 and poll['unread'] == 0
    assert poll['notice_preview']['from'] is None and 'sam handed in "Quiz 5"' in poll['notice_preview']['text']
    panel = teacher.get('/messages/notices').data.decode()
    assert 'sam handed in &#34;Quiz 5&#34;' in panel and 'notice-new' in panel
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
