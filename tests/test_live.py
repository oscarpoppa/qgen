"""Pages keep themselves up to date: each one names what it shows, the regular check-in
returns a fingerprint of that, and the page reloads (or offers to) when it changes."""
import re
from datetime import datetime, timedelta

from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)
from test_archive import ids
from test_dashboard import make_quiz, give


def watch(c, key):
    return c.get('/messages/poll?watch=' + key).get_json()['watch']


def drawn(page):
    """The page's key and the fingerprint it was drawn with (None, None if it has none)."""
    m = re.search(r'data-watch="([^"]+)" data-watch-state="([^"]+)"', page)
    return (m.group(1), m.group(2)) if m else (None, None)


def services(app):
    from app.qgen import services as S
    return S


def test_every_page_is_drawn_with_the_fingerprint_its_check_in_gives(app_db):
    # otherwise a page would reload itself at every check-in, for ever
    app, db = app_db
    from app.messages.models import Message
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teacher)
    essay = make_quiz(app, teacher, 'Essays', essay=True)
    with app.test_request_context():
        S = services(app)
        done = give(vq, 'sam')
        S.submit(done, {1: '4'})
        waiting = give(essay, 'sam')
        S.submit(waiting, {1: 'Light makes sugar.'})
        later = give(vq, 'sam', opens_at=datetime.now() + timedelta(days=1))
        S.archive_attempt(give(vq, 'kim'))
        db.session.commit()
    sam.post('/messages/reply', data={'body': 'A question'})
    from app.qgen.models import ArchivedAttempt
    aid = ArchivedAttempt.query.one().id
    pages = {
        teacher: ['/quiz/listuser', '/quiz/listuser/{}'.format(ids('sam')), '/quiz/review', '/quiz/listvq',
                  '/quiz/listvq/{}'.format(vq.id), '/quiz/listcq/{}'.format(done.id), '/quiz/take/{}'.format(later.id),
                  '/quiz/archive', '/quiz/archive/{}'.format(aid), '/userdet', '/messages',
                  '/messages/{}'.format(ids('sam'))],
        sam: ['/mypage', '/quiz/take/{}'.format(done.id), '/quiz/take/{}'.format(waiting.id),
              '/quiz/take/{}'.format(later.id)],
    }
    for client, urls in pages.items():
        for url in urls:
            for _ in range(2):
                key, state = drawn(client.get(url).data.decode())
                assert key, url
                assert watch(client, key) == state, url
    assert Message.query.count()  # (the conversation page marks it read before drawing: still equal)


def test_results_by_student_follow_what_happens(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teacher)
    everyone, just_sam = 'students', 'student:{}'.format(ids('sam'))
    seen = {k: watch(teacher, k) for k in (everyone, just_sam)}

    def changed(*keys):
        now = {k: watch(teacher, k) for k in (everyone, just_sam)}
        moved = {k for k in now if now[k] != seen[k]}
        seen.update(now)
        return moved == set(keys)

    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    assert changed(everyone, just_sam)  # assigned (the example from Nehad's page)
    cq = CQuiz.query.one()
    sam.get('/quiz/take/{}'.format(cq.id))
    assert changed(everyone, just_sam)  # started
    sam.post('/quiz/take/{}'.format(cq.id), data={'Number1': '4'})
    db.session.expire_all()
    assert CQuiz.query.one().completed and changed(everyone, just_sam)  # handed in and scored
    teacher.post('/quiz/retakerule/{}'.format(cq.id), data={'rule': 'average'})
    assert changed(everyone, just_sam)  # her own rule
    teacher.post('/quiz/editvquiz/{}'.format(vq.id), data={'title': 'Week 1', 'vplist': vq.vpid_lst, 'retake_rule': 'latest'})
    assert changed(everyone, just_sam)  # the quiz's rule (her override cleared)
    teacher.post('/quiz/retcq/{}'.format(cq.id))
    assert changed(everyone, just_sam)  # a retake
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('kim')]})
    assert changed(everyone)  # someone else: Sam's own page stays as it is
    teacher.post('/quiz/delcq/{}'.format(cq.id))
    assert changed(everyone, just_sam)  # deleted (archived)
    assert changed()  # and nothing moves by itself


def test_grading_queue_quiz_list_and_archive(app_db):
    app, db = app_db
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    essay = make_quiz(app, teacher, 'Essays', essay=True)
    before = {k: watch(teacher, k) for k in ('review', 'quizzes', 'quiz:{}'.format(essay.id), 'archive')}
    teacher.post('/quiz/assign', data={'vquiz': essay.id, 'users': [ids('sam')]})
    from app.qgen.models import CQuiz
    cq = CQuiz.query.one()
    assert watch(teacher, 'review') == before['review']  # nothing to grade yet
    assert watch(teacher, 'quizzes') != before['quizzes']  # "assigned 1 time"
    assert watch(teacher, 'quiz:{}'.format(essay.id)) != before['quiz:{}'.format(essay.id)]
    sam.post('/quiz/take/{}'.format(cq.id), data={'Number1': 'Light makes sugar.'})
    handed_in = watch(teacher, 'review')
    assert handed_in != before['review']
    with app.test_request_context():
        services(app).grade_essays(CQuiz.query.one(), {CQuiz.query.one().cproblems[0].id: {'credit': 90}}, finish=True)
    assert watch(teacher, 'review') == before['review']  # graded: gone from the list again
    archive = watch(teacher, 'archive')
    teacher.post('/quiz/delcq/{}'.format(cq.id))
    assert watch(teacher, 'archive') != archive
    from app.qgen.models import ArchivedAttempt
    a = ArchivedAttempt.query.one()
    one = watch(teacher, 'archived:{}'.format(a.id))
    teacher.post('/quiz/archive/{}/restore'.format(a.id))
    assert watch(teacher, 'archived:{}'.format(a.id)) != one  # restored: that page is out of date


def test_users_and_messages(app_db):
    app, db = app_db
    from app.qgen.models import Setting
    from app.user.models import User
    teacher = login(app, 'teach')
    users, inbox, convo = watch(teacher, 'users'), watch(teacher, 'messages'), watch(teacher, 'conversation:{}'.format(ids('sam')))
    sam = login(app, 'sam')
    sam.get('/mypage')
    assert watch(teacher, 'users') != users  # Sam is online now
    users = watch(teacher, 'users')
    Setting.put('class_code', 'oak-3')
    app.test_client().post('/register', data={'class_code': 'oak-3', 'username': 'lee', 'email': '',
                                              'password': 'long-enough', 'retype_password': 'long-enough'})
    assert User.query.filter_by(username='lee').count() == 1 and watch(teacher, 'users') != users  # signed up
    sam.post('/messages/reply', data={'body': 'Is it due Friday?'})
    assert watch(teacher, 'messages') != inbox and watch(teacher, 'conversation:{}'.format(ids('sam'))) != convo
    # "N min ago" ticking over doesn't reload the page every minute (the teacher stays online meanwhile)
    from app import live
    from flask_login import login_user
    sam_user = db.session.get(User, ids('sam'))
    sam_user.last_seen, sam_user.logged_in = datetime.now() - timedelta(minutes=10), True
    db.session.commit()
    with app.test_request_context():
        login_user(db.session.get(User, ids('teach')))
        now = datetime.now()
        assert live.state('users', now) == live.state('users', now + timedelta(seconds=90))


def test_a_students_own_pages(app_db):
    app, db = app_db
    from app import live
    from app.user.models import User
    from flask_login import login_user
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teacher)
    opens = datetime.now() + timedelta(hours=1)
    with app.test_request_context():
        cq = give(vq, 'sam', opens_at=opens)
        db.session.commit()
    key = 'attempt:{}'.format(cq.id)
    # the quiz opening is noticed on My quizzes and on its "opens at ..." page, which only offers it
    with app.test_request_context():
        login_user(db.session.get(User, ids('sam')))
        for k in ('mine', key):
            assert live.state(k, opens - timedelta(minutes=1)) != live.state(k, opens + timedelta(minutes=1))
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert "You can't start this quiz yet" in page and 'data-watch-ask' in page and 'Go to the quiz' in page
    cq.opens_at = None
    db.session.commit()
    # taking it: starting and saving answers don't change the student's own fingerprint...
    before = watch(sam, key)
    sam.get('/quiz/take/{}'.format(cq.id))
    teacher_view = watch(teacher, key)
    sam.post('/quiz/take/{}/save'.format(cq.id), data={'Number1': '5'})
    assert watch(sam, key) == before
    # ...but a teacher watching the attempt sees the answers come in
    assert watch(teacher, key) != teacher_view
    # the teacher deletes it while Sam is on the page: her page is told
    teacher.post('/quiz/delcq/{}'.format(cq.id))
    assert watch(sam, key) not in (before, None)
    page = sam.get('/quiz/take/{}'.format(cq.id), follow_redirects=True).data.decode()
    assert 'removed' in page


def test_who_may_follow_what(app_db):
    app, db = app_db
    teacher, sam, kim = login(app, 'teach'), login(app, 'sam'), login(app, 'kim')
    vq = make_quiz(app, teacher)
    with app.test_request_context():
        cq = give(vq, 'sam')
        db.session.commit()
    for key in ('students', 'student:{}'.format(ids('sam')), 'review', 'quizzes', 'archive', 'users', 'messages',
                'conversation:{}'.format(ids('sam'))):
        assert watch(sam, key) is None and watch(teacher, key) is not None, key
    assert watch(kim, 'attempt:{}'.format(cq.id)) is None  # someone else's attempt
    assert watch(sam, 'attempt:{}'.format(cq.id)) is not None
    for key in ('', 'nonsense', 'attempt', 'attempt:x', 'student:1;drop', 'mine:3'):
        assert watch(teacher, key) is None, key
    assert 'data-watch' not in teacher.get('/quiz/makevprob').data.decode()  # forms being written never reload
    r = app.test_client().get('/messages/poll?watch=students')
    assert r.status_code == 302


def test_a_teacher_taking_their_own_quiz_isnt_told_they_changed_it(app_db):
    """Their own saving doesn't change what their quiz page watches (as for a student);
    a teacher looking at someone else's attempt still follows the answers."""
    app, db = app_db
    teacher = login(app, 'teach')
    vq = make_quiz(app, teacher)
    mine, sams = give(vq, 'teach'), give(vq, 'sam')
    db.session.commit()
    key, state = drawn(teacher.get('/quiz/take/{}'.format(mine.id)).data.decode())
    assert key == 'attempt:{}'.format(mine.id) and watch(teacher, key) == state
    r = teacher.post('/quiz/take/{}/save'.format(mine.id), data={'Number1': '5', 'Number1_present': '1'})
    assert r.get_json()['ok']
    db.session.expire_all()
    assert mine.cproblems[0].submitted == '5'  # it was saved...
    assert watch(teacher, key) == state  # ...and that isn't "a change by the teacher"
    # their own My quizzes follows what happens to their attempts, as a student's does
    key, state = drawn(teacher.get('/mypage').data.decode())
    assert key == 'mine' and watch(teacher, 'mine') == state
    give(vq, 'teach')
    db.session.commit()
    assert watch(teacher, 'mine') != state
    sam = login(app, 'sam')
    sam.get('/quiz/take/{}'.format(sams.id))
    before = watch(teacher, 'attempt:{}'.format(sams.id))
    sam.post('/quiz/take/{}/save'.format(sams.id), data={'Number1': '5', 'Number1_present': '1'})
    assert watch(teacher, 'attempt:{}'.format(sams.id)) != before
