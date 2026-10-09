"""A quiz given to someone (student or teacher) is counted next to "My quizzes" in the
menu until it's handed in (not just until they look), and a teacher gets the notices about
quizzes they take."""
import re

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_archive import ids
from test_dashboard import make_quiz
from test_staff_messages import teachers

FETCH = {'X-Requested-With': 'fetch'}


def badge(page):
    """The count next to "My quizzes" in the menu, or None when it's hidden."""
    m = re.search(r'href="/mypage"[^>]*>My quizzes\s*<span class="count nav-quizzes"[^>]*? aria-label="(\d+) to do" (hidden)?', page)
    assert m, 'no My quizzes badge'
    return None if m.group(2) else int(m.group(1))


def assign(teacher, vq, *names):
    r = teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids(n) for n in names]})
    assert r.status_code in (200, 302)


def test_students_badge_until_the_quiz_is_done(app_db):
    app, db = app_db
    teach, sam, kim = login(app, 'teach'), login(app, 'sam'), login(app, 'kim')
    vq = make_quiz(app, teach)
    assert badge(sam.get('/profile').data.decode()) is None
    assert sam.get('/messages/poll').get_json()['quizzes'] == 0
    assign(teach, vq, 'sam')
    assert sam.get('/messages/poll').get_json()['quizzes'] == 1  # the open page's badge follows this
    assert kim.get('/messages/poll').get_json()['quizzes'] == 0
    page = sam.get('/profile').data.decode()
    assert badge(page) == 1 and 'Quizzes for you to do' in page  # on the Menu button too
    # opening My quizzes, or starting the quiz, doesn't clear it: only handing it in does
    assert badge(sam.get('/mypage').data.decode()) == 1
    from app.qgen.models import CQuiz
    from app.qgen import services as S
    cq = CQuiz.query.filter_by(assignee=ids('sam')).one()
    sam.post('/quiz/take/{}/start'.format(cq.id))
    assert sam.get('/messages/poll').get_json()['quizzes'] == 1
    S.submit(cq, {})
    assert sam.get('/messages/poll').get_json()['quizzes'] == 0
    # a retake is one to do again
    with app.test_request_context():
        S.retake(cq)
    assert sam.get('/messages/poll').get_json()['quizzes'] == 1


def test_teachers_get_the_badge_and_the_notice(app_db):
    app, db = app_db
    teachers(db, 'lee')
    teach, lee = login(app, 'teach'), login(app, 'lee')
    vq = make_quiz(app, teach)
    before = lee.get('/messages/poll').get_json()['notices']
    assign(teach, vq, 'lee', 'sam')
    got = lee.get('/messages/poll').get_json()
    assert got['quizzes'] == 1
    # their own "New quiz" notice, besides the usual "teach assigned ..." one; it pops up
    assert got['notices'] == before + 2
    assert got['notice_preview']['text'].startswith('New quiz: "Week 1"')
    panel = lee.get('/messages/notices').data.decode()
    assert 'New quiz: &#34;Week 1&#34;' in panel or 'New quiz: "Week 1"' in panel
    # only to the teacher it's for
    assert 'New quiz:' not in teach.get('/messages/notices').data.decode()
    assert teach.get('/messages/poll').get_json()['quizzes'] == 0
    # clicking it marks it read; opening the panel marks the rest
    from app.messages.models import Message
    own = Message.query.filter_by(kind='notice', student_id=ids('lee'), from_teacher=True).one()
    assert lee.post('/messages/notices/seen/{}'.format(own.id), data={}, headers=FETCH).get_json() == {'ok': True}
    assert lee.get('/messages/poll').get_json()['notices'] == before + 1
    lee.get('/messages/notices?seen=1')
    assert lee.get('/messages/poll').get_json()['notices'] == 0
    # another teacher can't touch it; clearing their own deletes it
    assert teach.post('/messages/notices/clear/{}'.format(own.id), data={}, headers=FETCH).status_code == 404
    assert lee.post('/messages/notices/clear/{}'.format(own.id), data={}, headers=FETCH).get_json()['cleared'] == 1
    assert db.session.get(Message, own.id) is None
    # "Clear all" clears both kinds
    assign(teach, vq, 'lee')
    assert lee.post('/messages/notices/clear', data={}, headers=FETCH).get_json()['cleared'] >= 2
    assert 'New quiz:' not in lee.get('/messages/notices').data.decode()
    # the badge is the same as a student's: counted by quiz (two tries at one quiz are one),
    # and still there after looking at My quizzes
    assert badge(lee.get('/dashboard').data.decode()) == 1
    lee.get('/mypage')
    assert badge(lee.get('/dashboard').data.decode()) == 1


def test_archived_quizzes_drop_out_and_restored_ones_come_back(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teach)
    assign(teach, vq, 'sam')
    from app.qgen.models import CQuiz, new_quizzes
    from app.qgen import services as S
    cq = CQuiz.query.filter_by(assignee=ids('sam')).one()
    a = S.archive_attempt(cq)
    db.session.commit()
    assert new_quizzes(ids('sam')) == 0
    S.restore_attempt(a)
    db.session.commit()
    assert new_quizzes(ids('sam')) == 1  # back, and still not done
    assign(teach, vq, 'sam')
    assert new_quizzes(ids('sam')) == 1  # another try at the same quiz: still one quiz
    from test_api import Api
    assert Api(app, 'sam').get('/my/quizzes').status_code == 200
    assert new_quizzes(ids('sam')) == 1  # looking (in the app too) doesn't clear it


def test_the_assigned_notice_opens_what_was_assigned(app_db):
    app, db = app_db
    from app.messages.models import Message
    from app.qgen.models import CQuiz
    from test_staff_messages import teachers
    teachers(db, 'lee')
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    shared = lambda: Message.query.filter_by(kind='notice', from_teacher=False).order_by(Message.id.desc()).first()
    # one student: their own copy of the quiz
    assign(teach, vq, 'sam')
    cq = CQuiz.query.filter_by(assignee=ids('sam')).one()
    assert shared().link == '/quiz/take/{}'.format(cq.id)
    page = teach.get(shared().link).data.decode()
    assert 'Only sam can submit it.' in page and CQuiz.query.get(cq.id).startdate is None  # a preview; looking doesn't start it
    # several: the quiz's results, with each one's copy
    assign(teach, vq, 'sam', 'kim')
    assert shared().link == '/quiz/results/{}'.format(vq.id)
    # a teacher given it: their results page (opening their own copy would start it)
    assign(teach, vq, 'lee')
    assert shared().link == '/quiz/listuser/{}'.format(ids('lee'))


def test_the_assigned_notice_shows_the_students_picture(app_db):
    app, db = app_db
    from app.messages.models import Message
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    shared = lambda: Message.query.filter_by(kind='notice', from_teacher=False).order_by(Message.id.desc()).first()
    assign(teach, vq, 'sam')
    assert shared().student_id == ids('sam')  # filed under sam: the panel shows sam's picture
    panel = teach.get('/messages/notices').data.decode()
    from app.icons import PATHS
    assert 'teach assigned' in panel and PATHS['users'] not in panel
    # sam never sees the teachers' notice about him
    sam = login(app, 'sam')
    assert 'teach assigned' not in sam.get('/messages/notices').data.decode()
    assert 'teach assigned' not in sam.get('/messages/panel').data.decode()
    # several students: a group icon
    assign(teach, vq, 'sam', 'kim')
    assert shared().student_id == ids('teach')
    assert '<span class="notice-icon" aria-hidden="true"><svg class="ico"' in teach.get('/messages/notices').data.decode()
