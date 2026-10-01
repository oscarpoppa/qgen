"""Subjects: the teacher's own lists for sorting problems and quizzes."""
from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)



def make_problems(teacher, *titles):
    from app.qgen.models import VProblem
    for t in titles:
        teacher.post('/quiz/makevprob', data=problem_form('numeric', t, 'What is 2 + 2?', '4', []))
    return {p.title: p for p in VProblem.query.all()}


def test_making_renaming_and_deleting_subjects(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup, VQGroup
    from app.qgen import services as S
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area')

    assert teacher.post('/quiz/subjects/problems/new', data={'name': '  Algebra   one '}).status_code == 302
    alg = VPGroup.query.one()
    assert alg.title == 'Algebra one'  # spaces tidied
    # same name in any case, empty and overlong names are refused
    for bad in ('ALGEBRA ONE', '   ', 'x' * 65):
        teacher.post('/quiz/subjects/problems/new', data={'name': bad})
    assert VPGroup.query.count() == 1
    # problem and quiz subjects are separate lists: the same name is fine there
    teacher.post('/quiz/subjects/quizzes/new', data={'name': 'Algebra one'})
    assert VQGroup.query.count() == 1

    teacher.post('/quiz/subjects/problems/{}/rename'.format(alg.id), data={'name': 'Algebra'})
    assert db.session.get(VPGroup, alg.id).title == 'Algebra'
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Geometry'})
    geo = VPGroup.query.filter_by(title='Geometry').one()
    teacher.post('/quiz/subjects/problems/{}/rename'.format(geo.id), data={'name': 'algebra'})  # taken
    assert db.session.get(VPGroup, geo.id).title == 'Geometry'

    # deleting a subject keeps its problems
    S.file_items('problems', [probs['Add'].id], db.session.get(VPGroup, alg.id))
    teacher.post('/quiz/subjects/problems/{}/delete'.format(alg.id))
    db.session.expire_all()
    assert db.session.get(VPGroup, alg.id) is None
    assert db.session.get(type(probs['Add']), probs['Add'].id) is not None
    assert probs['Add'].vpgroups == []

    # unknown kinds and subjects
    assert teacher.post('/quiz/subjects/students/new', data={'name': 'x'}).status_code == 404
    assert teacher.post('/quiz/subjects/problems/999/delete').status_code == 404


def test_filing_problems_into_several_subjects_and_listing_them(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area', 'Angles')
    for name in ('Algebra', 'Geometry'):
        teacher.post('/quiz/subjects/problems/new', data={'name': name})
    alg, geo = (VPGroup.query.filter_by(title=n).one() for n in ('Algebra', 'Geometry'))
    # new problems start with no subject
    assert all(not p.vpgroups for p in probs.values())

    # bulk: add, add again (harmless), and a problem in two subjects
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id, probs['Area'].id]})
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id]})
    teacher.post('/quiz/subjects/problems/file', data={'subject': geo.id, 'items': [probs['Area'].id, probs['Angles'].id]})
    db.session.expire_all()
    assert sorted(p.title for p in alg.vproblems) == ['Add', 'Area']
    assert sorted(p.title for p in geo.vproblems) == ['Angles', 'Area']

    page = lambda q='': teacher.get('/quiz/listvp' + q).data.decode()
    algebra = page('?subject={}'.format(alg.id))
    row = lambda t: 'aria-label="Tick “{}”"'.format(t)
    assert row('Add') in algebra and row('Area') in algebra and row('Angles') not in algebra
    assert 'Algebra (2)' in algebra and 'Geometry (2)' in algebra and 'All (3)' in algebra and 'No subject (0)' in algebra
    # remove from the open subject
    teacher.post('/quiz/subjects/problems/file', data={'remove_from': alg.id, 'items': [probs['Area'].id]})
    db.session.expire_all()
    assert [p.title for p in alg.vproblems] == ['Add']
    nosub = page('?subject=none')
    assert 'No subject (0)' in nosub  # Area is still in Geometry
    # the list remembers the last subject opened (here No subject), without asking
    assert '<option value="none" selected>' in page()
    page('?subject={}'.format(alg.id))
    assert '<option value="{}" selected>'.format(alg.id) in page()
    # nothing ticked, or no subject chosen: nothing happens
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id})
    teacher.post('/quiz/subjects/problems/file', data={'items': [probs['Angles'].id]})
    db.session.expire_all()
    assert [p.title for p in alg.vproblems] == ['Add']


def test_a_deleted_subject_falls_back_to_all(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    make_problems(teacher, 'Add')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Temp'})
    t = VPGroup.query.one()
    teacher.get('/quiz/listvp?subject={}'.format(t.id))
    teacher.post('/quiz/subjects/problems/{}/delete'.format(t.id))
    page = teacher.get('/quiz/listvp').data.decode()
    assert '<option value="all" selected>' in page and 'Add' in page
    assert '<option value="all" selected>' in teacher.get('/quiz/listvp?subject=nonsense').data.decode()


def test_edit_forms_file_items_and_save_returns_to_the_subject(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup, VQGroup, VProblem, VQuiz
    teacher = login(app, 'teach')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Algebra'})
    teacher.post('/quiz/subjects/quizzes/new', data={'name': 'Period 2'})
    alg, p2 = VPGroup.query.one(), VQGroup.query.one()
    form = problem_form('numeric', 'Filed', 'What is 2 + 2?', '4', [])
    assert 'name="subjects"' in teacher.get('/quiz/makevprob').data.decode()
    teacher.post('/quiz/makevprob', data=dict(form, subjects_shown='1', subjects=[str(alg.id)]))
    vp = VProblem.query.one()
    assert [g.title for g in vp.vpgroups] == ['Algebra']
    # the edit form shows it ticked; saving without ticks takes it out
    assert 'value="{}" checked'.format(alg.id) in teacher.get('/quiz/editvprob/{}'.format(vp.id)).data.decode()
    teacher.get('/quiz/listvp?subject={}'.format(alg.id))
    r = teacher.post('/quiz/editvprob/{}'.format(vp.id), data=dict(form, subjects_shown='1'))
    db.session.expire_all()
    assert vp.vpgroups == []
    # back on the list, still in Algebra
    assert '<option value="{}" selected>'.format(alg.id) in teacher.get(r.headers['Location']).data.decode()
    # a form without the Subjects row (e.g. an older page) leaves them alone
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [vp.id]})
    teacher.post('/quiz/editvprob/{}'.format(vp.id), data=form)
    db.session.expire_all()
    assert [g.title for g in vp.vpgroups] == ['Algebra']

    # quizzes the same way
    teacher.post('/quiz/makevquiz', data={'title': 'Q', 'vplist': str(vp.id), 'subjects_shown': '1', 'subjects': [str(p2.id)]})
    vq = VQuiz.query.one()
    assert [g.title for g in vq.vqgroups] == ['Period 2']
    # problem subjects can't be given to a quiz (ids from the other list are ignored)
    teacher.post('/quiz/editvquiz/{}'.format(vq.id), data={'title': 'Q', 'vplist': str(vp.id), 'subjects_shown': '1',
                                                           'subjects': ['999']})
    db.session.expire_all()
    assert vq.vqgroups == []


def test_quiz_builder_and_assign_page_offer_subjects(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VPGroup, VQGroup, VQuiz
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Algebra'})
    alg = VPGroup.query.one()
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id]})
    teacher.get('/quiz/listvp?subject={}'.format(alg.id))
    builder = teacher.get('/quiz/makevquiz').data.decode()
    # every problem is in the page (ticks survive switching), each knowing its subjects;
    # the menu opens on the subject last open on the Problems list
    assert 'id="builder-subject"' in builder and 'Add' in builder and 'Area' in builder
    assert 'data-subjects="{}"'.format(alg.id) in builder and 'data-subjects=""' in builder
    assert '<option value="{}" selected>Algebra (1)</option>'.format(alg.id) in builder

    for title in ('Q1', 'Q2'):
        teacher.post('/quiz/makevquiz', data={'title': title, 'vplist': str(probs['Add'].id)})
    teacher.post('/quiz/subjects/quizzes/new', data={'name': 'Period 2'})
    p2 = VQGroup.query.one()
    q1, q2 = (VQuiz.query.filter_by(title=t).one() for t in ('Q1', 'Q2'))
    teacher.post('/quiz/subjects/quizzes/file', data={'subject': p2.id, 'items': [q2.id]})
    teacher.get('/quiz/listvq?subject={}'.format(p2.id))
    page = teacher.get('/quiz/assign').data.decode()
    assert 'id="assign-subject"' in page and '<option value="{}" selected>Period 2 (1)</option>'.format(p2.id) in page
    assert '"{}": [{}]'.format(q2.id, p2.id) in page and '"{}": []'.format(q1.id) in page
    # a link for one quiz opens on All, with that quiz chosen
    page = teacher.get('/quiz/assign?vq={}'.format(q1.id)).data.decode()
    assert '<option value="all" selected>' in page and '<option selected value="{}">Q1</option>'.format(q1.id) in page
    # the server takes any quiz, whatever the menu showed
    sam_id = User.query.filter_by(username='sam').one().id
    teacher.post('/quiz/assign', data={'vquiz': q1.id, 'users': [sam_id]})
    assert len(q1.cquizzes) == 1
    # the API lists subjects too
    from app.api.serialize import problem_json, vquiz_json
    assert problem_json(probs['Add'])['subjects'] == [{'id': alg.id, 'name': 'Algebra'}]
    assert vquiz_json(q2)['subjects'] == [{'id': p2.id, 'name': 'Period 2'}]


def test_subject_changes_are_for_teachers_with_the_page_token(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    assert sam.post('/quiz/subjects/problems/new', data={'name': 'Mine'}).status_code in (302, 403)
    assert VPGroup.query.count() == 0
    assert sam.get('/quiz/listvp').status_code in (302, 403)
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        r = teacher.post('/quiz/subjects/problems/new', data={'name': 'NoToken'}, follow_redirects=True)
        assert b'out of date' in r.data
    finally:
        app.config['WTF_CSRF_ENABLED'] = False
    assert VPGroup.query.count() == 0
