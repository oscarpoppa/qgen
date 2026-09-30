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
    home = sam.get('/mypage').data.decode()
    assert 'Great &lt;b&gt;work&lt;/b&gt; today!' in home and 'msg-new' in home  # escaped, and marked new
    assert sam.get('/messages/poll').get_json()['unread'] == 0  # seeing it marks it read

    # kim can't see sam's messages
    kim = login(app, 'kim')
    assert 'Great' not in kim.get('/mypage').data.decode()
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
    assert 'No class Friday.' in kim.get('/mypage').data.decode()

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
    assert 'New quiz: &#34;Quiz 9&#34;' in sam.get('/mypage').data.decode()

    # deleting a student removes their conversation
    teacher.get('/deluser/{}'.format(kim_id))
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
    home = login(app, 'kim').get('/mypage').data.decode()
    assert 'pinned-list' in home and 'Test Friday!' in home
    assert teacher.get('/messages').data.decode().count('Unpin') == 2
    batch_msg = Message.query.filter_by(body='Test Friday!').first()
    teacher.post('/messages/pin/{}'.format(batch_msg.id), data={'pinned': '0'})
    assert Message.query.filter_by(body='Test Friday!', pinned=True).count() == 0
    assert 'pinned-list' not in login(app, 'kim').get('/mypage').data.decode()
    # a teacher account can't be chosen as a recipient
    teacher.post('/messages/send', data={'to': 'chosen', 'students': [str(sam_id), '1'], 'body': 'y'})
    assert Message.query.filter_by(body='y').count() == 0
    assert kim_id != sam_id
