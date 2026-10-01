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
    assert b'to the archive' in r.data
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
    assert b'Your teacher has removed this quiz attempt.' in r.data
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
    assert teacher.get('/quiz/archive/{}'.format(a.id)).status_code == 404


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
    # both attempts in one folder named after sam, marked as a deleted account
    assert page.count('account deleted') == 1 and '100%' in page and 'Not started' in page
    assert page.count('📁 sam</span>') == 1 and 'aria-label="2 archived"' in page
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


def test_the_archive_has_a_folder_for_each_student(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import CQuiz
    teacher = login(app, 'teach')
    vq, probs = setup_quiz(app, teacher, 'numeric')
    # every student has a folder, even with nothing in it yet; teachers don't
    page = teacher.get('/quiz/archive').data.decode()
    assert '📁 kim</span>' in page and '📁 sam</span>' in page and '📁 teach</span>' not in page
    assert page.index('📁 kim') < page.index('📁 sam') and 'Nothing archived for sam.' in page
    assert 'id="folder-student-{}" data-box="student-{}" data-empty'.format(ids('sam'), ids('sam')) in page
    # a new student gets one automatically
    u = User(username='ava', is_admin=False)
    u.set_password('pw-for-tests')
    db.session.add(u)
    db.session.commit()
    assert '📁 ava</span>' in teacher.get('/quiz/archive').data.decode()
    # a deleted attempt goes in its student's folder
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam'), ids('kim')]})
    teacher.post('/quiz/delcq/{}'.format(CQuiz.query.filter_by(assignee=ids('sam')).one().id))
    page = teacher.get('/quiz/archive').data.decode()
    sam = page.split('📁 sam</span>')[1].split('</details>')[0]
    kim = page.split('📁 kim</span>')[1].split('</details>')[0]
    assert 'Week 1' in sam and 'aria-label="1 archived"' in sam
    assert 'Week 1' not in kim and 'Nothing archived for kim.' in kim
    assert 'id="folder-student-{}" data-box="student-{}">'.format(ids('sam'), ids('sam')) in page  # not empty now


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
