"""Trash messages: written in the delete question, sent in one notice to every teacher (and the student, for his/her
attempt), kept with the item in the Trash and changeable there (the owner, 2026-10-29). Also Pending Quizzes' link."""

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_assign_pages import ids, quiz_of, copies


def _notices(student_id=None):
    from app.messages.models import Message
    q = Message.query.filter(Message.kind == 'notice')
    if student_id is not None:
        q = q.filter(Message.student_id == student_id)
    return [m.body for m in q.order_by(Message.id)]


def test_attempt_moved_to_trash_tells_teachers_and_the_student(app_db):
    from app.qgen.models import TrashNote, ArchivedAttempt
    app, db = app_db
    teacher = login(app, 'teach')
    vq, _ = quiz_of(teacher, 'M1')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    cq = copies(vq)[0]
    teacher.post('/quiz/delcq/{}'.format(cq.id), data={'trash_message': 'Given by mistake'})
    a = ArchivedAttempt.query.one()
    assert TrashNote.query.filter_by(kind='attempt', item_id=a.id).one().text == 'Given by mistake'
    bodies = _notices()
    assert 'teach moved sam’s attempt at “Q M1” to the Trash: “Given by mistake”' in bodies
    assert 'Your teacher took away your attempt at “Q M1”: “Given by mistake”' in bodies
    #the Trash shows it, as a note icon, and asks again with it when deleting for good
    trash = teacher.get('/quiz/archive').data.decode()
    assert 'Message from when it was moved to the Trash' in trash and 'Given by mistake' in trash
    assert 'data-trash-message-before="Given by mistake"' in trash
    teacher.post('/quiz/archive/{}/delete'.format(a.id), data={'trash_message': 'Not needed'})
    assert TrashNote.query.count() == 0
    assert 'teach deleted sam’s attempt at “Q M1” for good: “Not needed”' in _notices()


def test_empty_message_still_sends_the_notice(app_db):
    from app.qgen.models import TrashNote
    app, db = app_db
    teacher = login(app, 'teach')
    vq, _ = quiz_of(teacher, 'M2')
    teacher.post('/quiz/archivevq/{}'.format(vq.id), data={})
    assert 'teach moved the quiz “Q M2” to the Trash.' in _notices()
    assert TrashNote.query.count() == 0


def test_quiz_with_attempts_cant_be_deleted_for_good_from_the_trash(app_db):
    from app.qgen.models import VQuiz
    app, db = app_db
    teacher = login(app, 'teach')
    vq, _ = quiz_of(teacher, 'M3')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    teacher.post('/quiz/archivevq/{}'.format(vq.id), data={'trash_message': 'Old'})
    teacher.post('/quiz/removed/{}/delete'.format(vq.id), data={})
    assert db.session.get(VQuiz, vq.id) is not None
    page = teacher.get('/quiz/archive?section=quizzes').data.decode()
    assert 'Students have attempts at this quiz; move those to the Trash first' in page


def test_restore_drops_the_message(app_db):
    from app.qgen.models import TrashNote, VQuiz
    app, db = app_db
    teacher = login(app, 'teach')
    vq, _ = quiz_of(teacher, 'M4')
    teacher.post('/quiz/archivevq/{}'.format(vq.id), data={'trash_message': 'Later'})
    assert TrashNote.query.filter_by(kind='quiz', item_id=vq.id).count() == 1
    teacher.post('/quiz/removed/{}/back'.format(vq.id))
    assert db.session.get(VQuiz, vq.id).removed_at is None
    assert TrashNote.query.count() == 0


def test_move_all_to_trash_one_message_one_notice(app_db):
    from app.qgen.models import TrashNote
    app, db = app_db
    teacher = login(app, 'teach')
    vq, _ = quiz_of(teacher, 'M5')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    teacher.post('/quiz/takeaway/{}/{}'.format(vq.id, ids('sam')), data={'trash_message': 'Retired'})
    #(by their words: moving attempts to the Trash also clears the old notices about them, so the list isn't longer by 2)
    bodies = _notices()
    assert bodies.count('teach moved all 2 of sam’s attempts at “Q M5” to the Trash: “Retired”') == 1
    assert bodies.count('Your teacher took away your attempt at “Q M5”: “Retired”') == 1
    assert TrashNote.query.filter_by(kind='attempt').count() == 2


def test_trash_note_can_be_changed_by_a_teacher_only(app_db):
    from app.qgen.models import TrashNote
    app, db = app_db
    teacher = login(app, 'teach')
    vq, _ = quiz_of(teacher, 'M6')
    teacher.post('/quiz/archivevq/{}'.format(vq.id), data={'trash_message': 'First'})
    url = '/trash-note/quiz/{}'.format(vq.id)
    r = teacher.post(url, json={'note': 'Second'})
    assert r.get_json()['ok'] and TrashNote.query.one().text == 'Second'
    #(a student is turned away, and nothing changes)
    login(app, 'sam').post(url, json={'note': 'x'})
    assert TrashNote.query.one().text == 'Second'
    #(emptied, it goes)
    assert teacher.post(url, json={'note': ''}).get_json()['ok'] and TrashNote.query.count() == 0


def test_pending_quizzes_link_opens_the_quizs_folder(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    vq, _ = quiz_of(teacher, 'M7')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    page = teacher.get('/quiz/open').data.decode()
    assert '<h1>Pending Quizzes</h1>' in page
    assert 'href="/quiz/listuser/{}?folder=none&amp;show={}"'.format(ids('sam'), vq.id) in page
    assert '<strong>Q M7</strong>' in page
