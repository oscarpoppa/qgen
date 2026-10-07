"""The archive: deleted attempts (and deleted students' results) are kept, can be
looked at, restored, or deleted for good."""
from datetime import datetime

from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)


def setup_quiz(app, teacher, *qtypes):
    """A quiz with one problem of each type given; returns (quiz, [problems])."""
    from app.qgen.models import VProblem, VQuiz
    made = []
    for i, qt in enumerate(qtypes):
        if qt == 'essay':
            f = problem_form('essay', 'Essay {}'.format(i), 'Explain photosynthesis.')
        else:
            f = problem_form('numeric', 'Sum {}'.format(i), 'What is 2 + 2?', '4', [])
        teacher.post('/quiz/makevprob', data=f)
        made.append(VProblem.query.order_by(VProblem.id.desc()).first())
    teacher.post('/quiz/makevquiz', data={'title': 'Week 1', 'vplist': ','.join(str(p.id) for p in made),
                                          'shuffle_order': ''})
    return VQuiz.query.filter_by(title='Week 1').one(), made


def ids(name):
    from app.user.models import User
    return User.query.filter_by(username=name).one().id


def test_deleting_an_attempt_archives_it_and_restore_brings_it_back(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, ArchivedAttempt
    from app.qgen import services as S
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    vq, probs = setup_quiz(app, teacher, 'numeric', 'essay')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    cq = CQuiz.query.one()
    with app.test_request_context():
        S.submit(cq, {1: '4', 2: 'Plants turn light into sugar.'})
        essay = [cp for cp in cq.cproblems if cp.ordinal == 2][0]
        S.grade_essays(cq, {essay.id: {'credit': 60, 'feedback': 'Say more about water.',
                                       'highlights': [[0, 6, 'right'], [12, 17, 'wrong']]}}, finish=True)
        second = S.retake(cq)
    cqid, before = cq.id, sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    dates = (cq.startdate, cq.compdate, cq.create_date, cq.graded_date)
    assert '80%' in before

    # archive the first attempt
    r = teacher.post('/quiz/delcq/{}'.format(cqid), follow_redirects=True)
    assert b'to the Archive' in r.data
    db.session.expire_all()
    assert db.session.get(CQuiz, cqid) is None
    a = ArchivedAttempt.query.one()
    assert (a.original_id, a.student_name, a.quiz_title, a.score, a.completed) == (cqid, 'sam', 'Week 1', 80.0, True)
    # gone everywhere a live attempt shows
    home = sam.get('/mypage').data.decode()
    assert 'data-attempts="{}"'.format(second.id) in home
    results = teacher.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert '/quiz/take/{}"'.format(cqid) not in results and '/quiz/take/{}"'.format(second.id) in results
    from app.api.serialize import my_quizzes_json
    from app.user.models import User
    with app.test_request_context():
        listed = my_quizzes_json(db.session.get(User, ids('sam')))
    assert [att['id'] for q in listed for att in q['attempts']] == [second.id]
    # the student opening the old link is told plainly
    r = sam.get('/quiz/take/{}'.format(cqid), follow_redirects=True)
    assert b'Your teacher has taken this quiz away.' in r.data
    assert sam.post('/quiz/take/{}/save'.format(cqid), data={}).status_code == 410
    # a teacher opening it goes to the archived copy
    assert teacher.get('/quiz/take/{}'.format(cqid)).headers['Location'].endswith('/quiz/archive/{}'.format(a.id))
    # nobody else learns anything
    assert login(app, 'kim').get('/quiz/take/{}'.format(cqid)).status_code == 404

    # the archive lists it and shows the full results, highlights and comment included
    page = teacher.get('/quiz/archive').data.decode()
    assert 'sam' in page and 'Week 1' in page and '80%' in page and 'by teach' in page
    view = teacher.get('/quiz/archive/{}'.format(a.id)).data.decode()
    assert '80%' in view and 'Say more about water.' in view and 'hl-right' in view and 'hl-wrong' in view
    assert 'Correct answer' in view and 'Restore' in view

    # restore: back under the same number, as it was
    teacher.post('/quiz/archive/{}/restore'.format(a.id))
    db.session.expire_all()
    assert ArchivedAttempt.query.count() == 0
    back = db.session.get(CQuiz, cqid)
    assert back is not None and back.score == 80.0 and back.completed and back.assignee == ids('sam')
    essay = [cp for cp in back.cproblems if cp.ordinal == 2][0]
    assert (essay.credit, essay.feedback, essay.highlights) == (0.6, 'Say more about water.', [[0, 6, 'right'], [12, 17, 'wrong']])
    assert essay.submitted == 'Plants turn light into sugar.'
    assert (back.startdate, back.compdate, back.create_date, back.graded_date) == dates and back.compdate
    assert sam.get('/quiz/take/{}'.format(cqid)).data.decode().count('80%') >= 1
    home = sam.get('/mypage').data.decode()
    assert 'data-attempts="{},{}"'.format(cqid, second.id) in home


def test_unfinished_and_waiting_attempts_archive_and_show(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, ArchivedAttempt
    from app.qgen import services as S
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric', 'essay')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam'), ids('kim')]})
    sam_cq = CQuiz.query.filter_by(assignee=ids('sam')).one()
    kim_cq = CQuiz.query.filter_by(assignee=ids('kim')).one()
    with app.test_request_context():
        S.start(sam_cq)
        S.autosave(sam_cq, {1: '5'})
        S.submit(kim_cq, {1: '4', 2: 'Light.'})
    assert teacher.get('/messages/poll').get_json()['review'] == 1
    teacher.post('/quiz/delcq/{}'.format(sam_cq.id))
    teacher.post('/quiz/delcq/{}'.format(kim_cq.id))
    # the waiting one leaves the Review count
    assert teacher.get('/messages/poll').get_json()['review'] == 0
    sam_a = ArchivedAttempt.query.filter_by(student_name='sam').one()
    kim_a = ArchivedAttempt.query.filter_by(student_name='kim').one()
    page = teacher.get('/quiz/archive').data.decode()
    assert 'Not handed in' in page and 'Being graded' in page
    view = teacher.get('/quiz/archive/{}'.format(sam_a.id)).data.decode()
    assert 'not handed in' in view and 'not graded' in view and '5' in view
    view = teacher.get('/quiz/archive/{}'.format(kim_a.id)).data.decode()
    assert 'being graded' in view and 'Light.' in view
    # restored, kim's is waiting for grading again
    teacher.post('/quiz/archive/{}/restore'.format(kim_a.id))
    assert teacher.get('/messages/poll').get_json()['review'] == 1


def test_old_style_results_archive_and_show(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, ArchivedAttempt
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    cq = CQuiz.query.one()
    cq.completed, cq.score, cq.compdate = True, 75.0, datetime(2024, 3, 1, 10, 0)
    cq.transcript = '{% extends "base.html" %}{% block content %}<h1>{{ title }}</h1><p>Old record: 75%</p>{% endblock %}'
    db.session.commit()
    teacher.post('/quiz/delcq/{}'.format(cq.id))
    a = ArchivedAttempt.query.one()
    view = teacher.get('/quiz/archive/{}'.format(a.id)).data.decode()
    assert 'Old record: 75%' in view and '<h1>Week 1</h1>' in view and '{%' not in view
    teacher.post('/quiz/archive/{}/restore'.format(a.id))
    db.session.expire_all()
    assert db.session.get(CQuiz, cq.id).transcript.startswith('{% extends')


def test_delete_for_good(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, ArchivedAttempt
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    teacher.post('/quiz/delcq/{}'.format(CQuiz.query.one().id))
    a = ArchivedAttempt.query.one()
    assert 'Delete for good' in teacher.get('/quiz/archive').data.decode()
    teacher.post('/quiz/archive/{}/delete'.format(a.id))
    assert ArchivedAttempt.query.count() == 0
    #gone: back to the Archive with a word about it, not "Not found"
    r = teacher.get('/quiz/archive/{}'.format(a.id))
    assert r.status_code == 302 and r.headers['Location'].endswith('/quiz/archive')


def test_deleting_a_student_keeps_their_results(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import CQuiz, ArchivedAttempt
    from app.qgen import services as S
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    sam_id = ids('sam')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam_id]})
    with app.test_request_context():
        S.submit(CQuiz.query.one(), {1: '4'})
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam_id]})  # a second, unstarted one
    assert 'Their quiz results are kept in the Archive.' in teacher.get('/userdet').data.decode()
    teacher.post('/deluser/{}'.format(sam_id))
    db.session.expire_all()
    assert db.session.get(User, sam_id) is None and CQuiz.query.count() == 0
    rows = ArchivedAttempt.query.order_by(ArchivedAttempt.original_id).all()
    assert [(r.student_name, r.reason) for r in rows] == [('sam', 'student deleted')] * 2
    page = teacher.get('/quiz/archive').data.decode()
    # both attempts stay in sam's folder (it keeps its name), each marked as a deleted account
    assert page.count('account deleted') == 2 and '100%' in page and 'Not started' in page
    from test_subjects import side_counts
    assert side_counts(page).get('sam') == 2
    view = teacher.get('/quiz/archive/{}'.format(rows[0].id)).data.decode()
    assert '100%' in view and "account was deleted" in view
    # can't be restored, even to a new account with the same name
    u = User(username='sam', is_admin=False)
    u.set_password('pw-for-tests')
    db.session.add(u)
    db.session.commit()
    r = teacher.post('/quiz/archive/{}/restore'.format(rows[0].id), follow_redirects=True)
    assert b'account was deleted' in r.data
    assert ArchivedAttempt.query.count() == 2 and CQuiz.query.count() == 0


def test_deleting_a_quiz_or_problem_an_archived_attempt_uses(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, ArchivedAttempt, VQuiz, VProblem
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    teacher.post('/quiz/delcq/{}'.format(CQuiz.query.one().id))
    a = ArchivedAttempt.query.one()
    # the delete questions warn
    assert '1 archived attempt uses this quiz; after deleting it it can still be viewed but not restored.' in \
        teacher.get('/quiz/listvq').data.decode()
    teacher.post('/quiz/delvq/{}'.format(vq.id))
    db.session.expire_all()
    assert db.session.get(VQuiz, vq.id) is None
    assert '1 archived attempt uses this problem' in teacher.get('/quiz/listvp').data.decode()
    teacher.post('/quiz/delvp/{}'.format(probs[0].id))
    db.session.expire_all()
    assert db.session.get(VProblem, probs[0].id) is None
    # still viewable; restore says why not
    page = teacher.get('/quiz/archive').data.decode()
    assert 'quiz deleted' in page and 'disabled' in page
    view = teacher.get('/quiz/archive/{}'.format(a.id)).data.decode()
    assert 'Week 1' in view and 'the quiz “Week 1” was deleted'.replace('“', '"').replace('”', '"') in view.replace('&#34;', '"')
    r = teacher.post('/quiz/archive/{}/restore'.format(a.id), follow_redirects=True)
    assert b'was deleted' in r.data and ArchivedAttempt.query.count() == 1


def test_restore_refused_when_a_problem_is_gone(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, ArchivedAttempt
    from app.qgen import services as S
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric', 'numeric')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    teacher.post('/quiz/delcq/{}'.format(CQuiz.query.one().id))
    a = ArchivedAttempt.query.one()
    # take a problem out of the quiz, then delete it
    teacher.post('/quiz/editvquiz/{}'.format(vq.id), data={'title': 'Week 1', 'vplist': str(probs[1].id)})
    teacher.post('/quiz/delvp/{}'.format(probs[0].id))
    assert '1 of its problems was deleted' in S.restore_blocker(a)


def test_the_archive_is_for_teachers(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, ArchivedAttempt
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    teacher.post('/quiz/delcq/{}'.format(CQuiz.query.one().id))
    a = ArchivedAttempt.query.one()
    for url in ('/quiz/archive', '/quiz/archive/{}'.format(a.id)):
        assert sam.get(url).status_code in (302, 403)
    sam.post('/quiz/archive/{}/restore'.format(a.id))
    sam.post('/quiz/archive/{}/delete'.format(a.id))
    assert ArchivedAttempt.query.count() == 1 and CQuiz.query.count() == 0
    assert '>Archive</a>' in teacher.get('/mypage').data.decode()
    assert '>Archive</a>' not in sam.get('/mypage').data.decode()
    # forged forms are refused
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        teacher.post('/quiz/archive/{}/delete'.format(a.id), data={'csrf_token': 'forged'})
    finally:
        app.config['WTF_CSRF_ENABLED'] = False
    assert ArchivedAttempt.query.count() == 1


def test_archive_through_the_api(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, ArchivedAttempt
    from app.api.models import ApiToken
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    cqid = CQuiz.query.one().id
    from app.user.models import User
    t_token = ApiToken.issue(db.session.get(User, ids('teach')), 'test')[1]
    s_token = ApiToken.issue(db.session.get(User, ids('sam')), 'test')[1]
    T = {'Authorization': 'Bearer ' + t_token}
    S_ = {'Authorization': 'Bearer ' + s_token}
    c = app.test_client()
    assert c.delete('/api/v2/attempts/{}'.format(cqid), headers=T).status_code == 204
    listed = c.get('/api/v2/archive', headers=T).get_json()['archive']
    assert [(x['attempt_id'], x['student_name'], x['restore_blocked']) for x in listed] == [(cqid, 'sam', None)]
    # narrowed by the quiz's label (?subject= still works for older scripts)
    from app.qgen import services as Svc
    lab = Svc.create_subject('quizzes', 'Period 2')
    for q in ('label=none', 'subject=none'):
        assert len(c.get('/api/v2/archive?' + q, headers=T).get_json()['archive']) == 1
    for q in ('label={}', 'subject={}'):
        assert c.get('/api/v2/archive?' + q.format(lab.id), headers=T).get_json()['archive'] == []
    one = c.get('/api/v2/archive/{}'.format(listed[0]['id']), headers=T).get_json()
    assert 'Week 1' in one['results_html']
    r = c.get('/api/v2/my/attempts/{}'.format(cqid), headers=S_)
    assert r.status_code == 410 and 'removed' in r.get_json()['error']['message']
    assert c.get('/api/v2/archive', headers=S_).status_code == 403
    assert c.post('/api/v2/archive/{}/restore'.format(listed[0]['id']), headers=T).status_code == 200
    assert c.get('/api/v2/my/attempts/{}'.format(cqid), headers=S_).status_code == 200
    c.delete('/api/v2/attempts/{}'.format(cqid), headers=T)
    aid = ArchivedAttempt.query.one().id
    assert c.delete('/api/v2/archive/{}'.format(aid), headers=T).status_code == 204
    assert ArchivedAttempt.query.count() == 0


def archive_view(teacher, folder='all'):
    """(the page, the attempts it lists as "student: quiz") for the Archive's ?folder=."""
    import re
    page = teacher.get('/quiz/archive' + ('?folder={}'.format(folder) if folder is not None else '')).data.decode()
    return page, re.findall(r'aria-label="Check ([^’]+)’s “([^”]+)”"', page)


def test_the_archive_has_a_folder_for_each_student(app_db):
    app, db = app_db
    from test_subjects import side_counts
    from app.user.models import User
    from app.qgen.models import CQuiz, ArchiveFolder
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    # every student has a folder (👤), even with nothing in it yet; teachers don't
    page, _ = archive_view(teacher)
    counts = side_counts(page)
    assert 'kim' in counts and 'sam' in counts and 'teach' not in counts
    assert page.index('<span class="side-name">kim') < page.index('<span class="side-name">sam') and '👤' in page
    sam_folder = ArchiveFolder.query.filter_by(student_id=ids('sam')).one()
    assert 'Nothing archived for sam yet.' in archive_view(teacher, sam_folder.id)[0]
    # a new student gets one automatically
    u = User(username='ava', is_admin=False)
    u.set_password('pw-for-tests')
    db.session.add(u)
    db.session.commit()
    assert 'ava' in side_counts(archive_view(teacher)[0])
    # an archived attempt goes in its student's folder
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam'), ids('kim')]})
    teacher.post('/quiz/delcq/{}'.format(CQuiz.query.filter_by(assignee=ids('sam')).one().id))
    kim_folder = ArchiveFolder.query.filter_by(student_id=ids('kim')).one()
    assert archive_view(teacher, sam_folder.id)[1] == [('sam', 'Week 1')]
    assert archive_view(teacher, kim_folder.id)[1] == [] and side_counts(archive_view(teacher)[0])['sam'] == 1
    # grouped by the month it was archived
    assert '<strong>{:%B %Y}</strong>'.format(__import__('datetime').datetime.now()) in archive_view(teacher)[0]


def test_archive_folders_can_be_made_renamed_moved_and_removed(app_db):
    app, db = app_db
    from test_subjects import side_counts
    from app.qgen.models import CQuiz, ArchiveFolder, ArchivedAttempt
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam'), ids('kim')]})
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    for cq in CQuiz.query.all():
        teacher.post('/quiz/delcq/{}'.format(cq.id))
    sam_f = ArchiveFolder.query.filter_by(student_id=ids('sam')).one()
    kim_f = ArchiveFolder.query.filter_by(student_id=ids('kim')).one()
    page, _ = archive_view(teacher, sam_f.id)
    assert 'Folder options' in page and 'Remove the folder “sam”? Nothing in it is deleted' in page

    # your own folder, and moving attempts into it
    teacher.post('/quiz/archive/folders/new', data={'name': '2025-26'})
    year = ArchiveFolder.query.filter_by(name='2025-26').one()
    assert year.student_id is None
    for bad in ('2025-26', ' not in a folder ', '', 'x' * 65):   # taken, kept for Not in a folder, empty, too long
        teacher.post('/quiz/archive/folders/new', data={'name': bad})
    assert ArchiveFolder.query.count() == 3
    sams = [a.id for a in ArchivedAttempt.query.filter_by(folder_id=sam_f.id)]
    teacher.post('/quiz/archive/move', data={'folder': str(year.id), 'items': sams[:1]})
    assert ArchivedAttempt.query.filter_by(folder_id=year.id).count() == 1
    # one at a time ("Move to…", or a drag)
    r = teacher.post('/quiz/archive/folders/move', data={'attempt': sams[1], 'to': year.id, 'view': sam_f.id})
    assert r.headers['Location'].endswith('/quiz/archive?folder={}&moved=attempt:{}'.format(sam_f.id, sams[1]))
    assert ArchivedAttempt.query.filter_by(folder_id=year.id).count() == 2
    teacher.post('/quiz/archive/folders/move', data={'attempt': sams[1], 'to': sam_f.id})

    # folders inside folders: a student's folder can go in yours
    teacher.post('/quiz/archive/folders/move', data={'folder': kim_f.id, 'to': year.id})
    db.session.expire_all()
    assert db.session.get(ArchiveFolder, kim_f.id).parent_id == year.id
    assert side_counts(archive_view(teacher)[0])['2025-26'] == 2  # its own, and kim's inside it
    FETCH = {'X-Requested-With': 'fetch'}
    res = teacher.post('/quiz/archive/folders/move', data={'folder': year.id, 'to': kim_f.id}, headers=FETCH)
    assert res.status_code == 400 and 'inside itself' in res.get_json()['error']

    # removing a folder: what's in it moves up a level (here, to the top: not in a folder)
    r = teacher.post('/quiz/archive/folders/{}/delete'.format(year.id), follow_redirects=True)
    assert b'moved up a level' in r.data
    db.session.expire_all()
    assert db.session.get(ArchiveFolder, year.id) is None and db.session.get(ArchiveFolder, kim_f.id).parent_id is None
    assert ArchivedAttempt.query.filter_by(folder_id=None).count() == 1
    assert len(archive_view(teacher, 'main')[1]) == 1
    teacher.post('/quiz/archive/move', data={'folder': 'top', 'items': sams[1:]})
    assert ArchivedAttempt.query.filter_by(folder_id=None).count() == 2

    # removing a student's folder: gone (not made again on its own) until their next archived attempt
    teacher.post('/quiz/archive/folders/{}/delete'.format(sam_f.id))
    assert 'sam' not in side_counts(archive_view(teacher)[0])
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    teacher.post('/quiz/delcq/{}'.format(CQuiz.query.one().id))
    assert side_counts(archive_view(teacher)[0])['sam'] == 1                                # only the new one
    assert ArchivedAttempt.query.filter_by(folder_id=None).count() == 2                  # older ones stay put

    # renaming a student's folder keeps it theirs: their next archived attempts go there too
    teacher.post('/quiz/archive/folders/{}/rename'.format(kim_f.id), data={'name': 'Kim - Period 2'})
    db.session.expire_all()
    renamed = db.session.get(ArchiveFolder, kim_f.id)
    assert renamed.name == 'Kim - Period 2' and renamed.student_id == ids('kim') and renamed.own_name
    counts = side_counts(archive_view(teacher)[0])
    assert 'Kim - Period 2' in counts and 'kim' not in counts
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('kim')]})
    teacher.post('/quiz/delcq/{}'.format(CQuiz.query.one().id))
    assert ArchivedAttempt.query.filter_by(folder_id=kim_f.id).count() == 2
    assert ArchiveFolder.query.filter_by(student_id=ids('kim')).count() == 1
    # names must stay different, and a forged form does nothing
    teacher.post('/quiz/archive/folders/new', data={'name': 'Spare'})
    teacher.post('/quiz/archive/folders/{}/rename'.format(kim_f.id), data={'name': 'spare'})
    db.session.expire_all()
    assert db.session.get(ArchiveFolder, kim_f.id).name == 'Kim - Period 2'
    assert login(app, 'sam').post('/quiz/archive/folders/new', data={'name': 'Mine'}).status_code in (302, 403)
    assert ArchiveFolder.query.filter_by(name='Mine').count() == 0

def test_an_archived_attempt_is_kept_as_a_small_readable_record(app_db):
    import json
    app, db = app_db
    from app.qgen.models import CQuiz, ArchivedAttempt
    from app.qgen import services as S
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric', 'essay')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    cq = CQuiz.query.one()
    with app.test_request_context():
        S.submit(cq, {1: '4', 2: 'Plants <b>use</b> light.'})
    stored_page = len(cq.transcript or '')
    teacher.post('/quiz/delcq/{}'.format(cq.id))
    a = ArchivedAttempt.query.one()
    record = json.loads(a.data)                       # plain JSON anyone can read
    assert record['v'] == 2 and [p['qtype'] for p in record['problems']] == ['numeric', 'essay']
    assert '<div' not in a.data and '<section' not in a.data and 'class=' not in a.data  # no page markup
    assert record['attempt']['transcript'] in (None, '<!--transcript v2-->')
    assert 'Plants <b>use</b> light.' in a.data                                          # the answer, as written
    assert len(a.data) < 2000 and (not stored_page or len(a.data) < stored_page + 1500)
    # the page drawn from it shows everything, the student's answer still escaped
    view = teacher.get('/quiz/archive/{}'.format(a.id)).data.decode()
    assert 'Plants &lt;b&gt;use&lt;/b&gt; light.' in view and 'Correct answer' in view


def test_student_folders_follow_the_student(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import CQuiz, ArchiveFolder
    from app.api.serialize import archived_json
    from app.qgen.models import ArchivedAttempt
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    teacher.get('/quiz/archive')
    sam_f = ArchiveFolder.query.filter_by(student_id=ids('sam')).one()
    # saving the same name keeps it the student's folder
    teacher.post('/quiz/archive/folders/{}/rename'.format(sam_f.id), data={'name': 'sam'})
    db.session.expire_all()
    assert db.session.get(ArchiveFolder, sam_f.id).student_id == ids('sam')
    # the student's username changes: their folder follows
    u = db.session.get(User, ids('sam'))
    u.username = 'samuel'
    db.session.commit()
    from test_subjects import side_counts
    counts = side_counts(teacher.get('/quiz/archive').data.decode())
    assert 'samuel' in counts and 'sam' not in counts
    # the API says which folder an attempt is in
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('samuel')]})
    teacher.post('/quiz/delcq/{}'.format(CQuiz.query.one().id))
    assert archived_json(ArchivedAttempt.query.one())['folder'] == 'samuel'


def test_the_archives_when_column_keeps_each_date_on_one_line(app_db):
    """"Taken <date>" and "Archived <date>" are never broken in two; who archived it goes below."""
    import re
    app, db = app_db
    from app.qgen.models import CQuiz
    from app.qgen import services as S
    teacher = login(app, 'teach')
    login(app, 'sam')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    cq = CQuiz.query.one()
    with app.test_request_context():
        S.submit(cq, {1: '4'})
    teacher.post('/quiz/delcq/{}'.format(cq.id))
    page = archive_view(teacher)[0]
    when = re.search(r'<td data-label="When"[^>]*>(.*?)</td>', page, re.S).group(1)
    assert re.search(r'<span class="nowrap">Taken [^<]+</span><br>', when)
    assert re.search(r'<span class="nowrap">Archived [^<]+</span><br>by teach', when)
    assert 'class="archive-table"' in page
