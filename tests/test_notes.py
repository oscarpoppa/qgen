"""Teachers' notes on problems, quizzes, pictures and files, and workbooks, as People's; and the teacher's note to the
students on an assigned quiz, which they see (the owner, 2026-10-28)."""
from test_flow import app_db, login  # noqa: F401  (fixture)
from test_assign_pages import ids, quiz_of, copies


def test_teachers_notes_on_problems_and_quizzes(app_db):
    """Saved as typed, only by teachers; the row shows its mark and its Notes card; the Dashboard lists them."""
    from app.qgen.models import VProblem, VQuiz
    app, db = app_db
    teacher = login(app, 'teach')
    vq, probs = quiz_of(teacher, 'N1', 'N2')
    r = teacher.post('/notes/problem/{}'.format(probs[0].id), json={'note': 'This problem needs to be fixed.'})
    assert r.get_json()['ok'] and 'Changed' in r.get_json()['changed']
    assert teacher.post('/notes/quiz/{}'.format(vq.id), json={'note': 'This quiz needs work.'}).get_json()['ok']
    assert db.session.get(VProblem, probs[0].id).teacher_note == 'This problem needs to be fixed.'
    assert db.session.get(VQuiz, vq.id).teacher_note_by_id == ids('teach')
    assert teacher.post('/notes/nothing/1', json={'note': 'x'}).status_code == 404
    page = teacher.get('/quiz/listvp').data.decode()
    assert 'data-note-text="This problem needs to be fixed."' in page and 'data-note-placeholder="Only teachers see this"' in page
    assert 'title="Note: This problem needs to be fixed."' not in page  # (no mark in the title column beside the Note icon)
    dash = teacher.get('/dashboard').data.decode()
    assert 'Problem and Quiz Notes' in dash and 'This quiz needs work.' in dash and '/quiz/listvq?show={}'.format(vq.id) in dash
    # a student can't write one
    sam = login(app, 'sam')
    r = sam.post('/notes/problem/{}'.format(probs[1].id), json={'note': 'mine'})
    assert r.status_code in (302, 403) and db.session.get(VProblem, probs[1].id).teacher_note is None


def test_a_note_to_the_students_on_an_assigned_quiz(app_db):
    """One note for everyone given the quiz in the same Assign: they see it on the start card, the quiz, its results, My
    quizzes and Home; a teacher changes it for all of them from a copy's row; a retake keeps it."""
    from app.qgen import services as S
    app, db = app_db
    teacher = login(app, 'teach')
    vq, probs = quiz_of(teacher, 'S1')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam'), ids('kim')], 'assign_note': 'Give this a try.'})
    a, b = copies(vq)
    assert a.assign_note == b.assign_note == 'Give this a try.' and a.assign_group and a.assign_group == b.assign_group
    sam = login(app, 'sam')
    start = sam.get('/quiz/take/{}'.format(a.id)).data.decode()
    assert 'From your teacher' in start and 'Give this a try.' in start
    assert 'Give this a try.' in sam.get('/mypage').data.decode()
    home = sam.get('/home').data.decode()
    assert 'popovertarget="note-pop-{}"'.format(a.id) in home and 'Note from your teacher' in home
    # the teacher changes it from sam's row: kim's changes too
    hist = teacher.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert 'Note to the Student' in hist and '/quiz/assign-note/{}'.format(a.id) in hist
    assert teacher.post('/quiz/assign-note/{}'.format(a.id), json={'note': 'You can do it.'}).get_json()['ok']
    db.session.expire_all()
    assert [c.assign_note for c in copies(vq)] == ['You can do it.', 'You can do it.']
    assert sam.post('/quiz/assign-note/{}'.format(a.id), json={'note': 'no'}).status_code in (302, 403)
    # a retake keeps it
    a.completed = True
    db.session.commit()
    with app.test_request_context():
        new = S.retake(a)
    assert new.assign_note == 'You can do it.' and new.assign_group == a.assign_group
    # its results show it
    assert 'You can do it.' in teacher.get('/quiz/take/{}'.format(a.id)).data.decode()


def test_notes_open_from_an_icon_with_the_rows_icons(app_db):
    """A row's note is an icon in its own Note column, a gold star note when there's one, opening
    a dialog (static/js/personnote.js); the open row has no note box; none in the Trash (the owner, 2026-10-29, To do 77)."""
    import re
    app, db = app_db
    teacher = login(app, 'teach')
    vq, probs = quiz_of(teacher, 'K1', 'K2')
    teacher.post('/notes/problem/{}'.format(probs[0].id), json={'note': 'Check the units.'})
    page = teacher.get('/quiz/listvp').data.decode()
    assert 'class="person-note card"' not in page and 'textarea' not in page.split('<table', 1)[1].split('</table>', 1)[0]
    assert 'data-note-text="Check the units."' in page and 'note-open has-note' in page
    assert '#i-lc-sticky-note-star' in page  # (written in: the gold sticky note with a star, D12)
    assert 'title="Notes: about “K1”, for teachers only"' in page and 'data-note-heading="Notes about “K1”"' in page
    # (in its own Note column, sortable, notes first; not with the row's icons: the owner, 2026-10-29, D29–D31)
    row = page.split('data-item="{}"'.format(probs[0].id), 1)[1].split('</tr>', 1)[0]
    assert 'class="note-col" data-sort="0"' in row and 'note-open' not in row.split('class="actions"', 1)[1]
    assert '<th data-sort-key="note">Note</th>' in page
    first = teacher.get('/quiz/listvp?sort=note&dir=asc').data.decode()
    assert first.index('data-item="{}"'.format(probs[0].id)) < first.index('data-item="{}"'.format(probs[1].id))
    for url in ('/quiz/listvq', '/people'):
        assert '<th data-sort-key="note">Note</th>' in teacher.get(url).data.decode()
    # the Trash: no Note icon
    teacher.post('/quiz/archivevp/{}'.format(probs[1].id))
    teacher.post('/notes/problem/{}'.format(probs[1].id), json={'note': 'Old one.'})
    trash = teacher.get('/quiz/archive?section=problems').data.decode()
    assert 'note-open' not in trash and 'title="Note: Old one."' not in trash  # (no mark by the name either: the owner, 2026-10-29)
