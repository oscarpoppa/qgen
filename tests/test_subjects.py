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


def boxes_on(page):
    """{container name: [titles of the rows in it]} from a Problems or Quizzes page."""
    import re
    out = {}
    for m in re.finditer(r'<details class="card subject-box[^"]*" id="subject-[^"]+"[^>]*>(.*?)</details>\s*(?=<details class="card subject-box|</div>)', page, re.S):
        body = m.group(1)
        name = re.search(r'<span class="box-name">(?:📁 |📥 )([^<]+)</span>', body).group(1)
        out[name] = re.findall(r'aria-label="Tick “([^”]+)”"', body)
    return out


def test_problems_page_shows_subject_containers(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area', 'Angles')
    # no subjects yet: everything is in Unsorted
    assert boxes_on(teacher.get('/quiz/listvp').data.decode()) == {'Unsorted': ['Angles', 'Area', 'Add']}
    for name in ('Geometry', 'Algebra'):
        teacher.post('/quiz/subjects/problems/new', data={'name': name})
    alg, geo = (VPGroup.query.filter_by(title=n).one() for n in ('Algebra', 'Geometry'))

    # bulk: add, add again (harmless), and a problem in two subjects
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id, probs['Area'].id]})
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id], 'action': 'add'})
    teacher.post('/quiz/subjects/problems/file', data={'subject': geo.id, 'items': [probs['Area'].id, probs['Angles'].id]})
    page = teacher.get('/quiz/listvp').data.decode()
    # containers by name; a problem is only in its containers; Unsorted is gone when empty
    assert boxes_on(page) == {'Algebra': ['Area', 'Add'], 'Geometry': ['Angles', 'Area']}
    assert 'id="subject-unsorted"' not in page
    assert 'aria-label="2 problems"' in page and 'Open all' in page and 'Close all' in page
    # remove from a subject: back to Unsorted if it's in no other
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id], 'action': 'remove'})
    assert boxes_on(teacher.get('/quiz/listvp').data.decode()) == {'Algebra': ['Area'], 'Geometry': ['Angles', 'Area'],
                                                                     'Unsorted': ['Add']}
    # an empty subject still has its container
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Calculus'})
    page = teacher.get('/quiz/listvp').data.decode()
    assert boxes_on(page)['Calculus'] == [] and 'Empty. Tick problems' in page
    # nothing ticked, or no subject chosen: nothing happens
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id})
    teacher.post('/quiz/subjects/problems/file', data={'items': [probs['Angles'].id]})
    db.session.expire_all()
    assert [p.title for p in alg.vproblems] == ['Area']


def test_quizzes_page_shows_subject_containers(app_db):
    app, db = app_db
    from app.qgen.models import VQGroup, VQuiz
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add')
    for t in ('Q1', 'Q2'):
        teacher.post('/quiz/makevquiz', data={'title': t, 'vplist': str(probs['Add'].id)})
    teacher.post('/quiz/subjects/quizzes/new', data={'name': 'Period 2'})
    p2 = VQGroup.query.one()
    teacher.post('/quiz/subjects/quizzes/file', data={'subject': p2.id, 'items': [VQuiz.query.filter_by(title='Q2').one().id]})
    assert boxes_on(teacher.get('/quiz/listvq').data.decode()) == {'Period 2': ['Q2'], 'Unsorted': ['Q1']}


def test_deleting_a_subject_keeps_its_items_in_unsorted(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Temp'})
    t = VPGroup.query.one()
    teacher.post('/quiz/subjects/problems/file', data={'subject': t.id, 'items': [probs['Add'].id]})
    page = teacher.get('/quiz/listvp').data.decode()
    assert 'Its 1 problem moves to Unsorted (unless also in another subject).' in page
    assert 'aria-label="Rename the subject “Temp”"' in page and 'aria-label="Delete the subject “Temp”"' in page
    teacher.post('/quiz/subjects/problems/{}/delete'.format(t.id))
    assert boxes_on(teacher.get('/quiz/listvp').data.decode()) == {'Unsorted': ['Add']}


def test_new_items_must_be_given_a_subject(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup, VQGroup, VProblem, VQuiz
    teacher = login(app, 'teach')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Algebra'})
    alg = VPGroup.query.one()
    form = problem_form('numeric', 'Filed', 'What is 2 + 2?', '4', [])
    page = teacher.get('/quiz/makevprob').data.decode()
    assert 'required: where should this problem go?' in page and 'name="unsorted"' in page and 'name="new_subject"' in page

    # no answer: not saved, and asked again
    r = teacher.post('/quiz/makevprob', data=dict(form, subjects_shown='1'))
    assert VProblem.query.count() == 0
    assert 'Choose a subject for this problem, or Unsorted to file it later.' in r.data.decode()
    # a subject: saved in it, and the list opens where it is
    r = teacher.post('/quiz/makevprob', data=dict(form, subjects_shown='1', subjects=[str(alg.id)]))
    vp = VProblem.query.one()
    assert [g.title for g in vp.vpgroups] == ['Algebra']
    assert r.headers['Location'].endswith('/quiz/listvp?show={}'.format(vp.id))
    assert 'data-item="{}" data-show'.format(vp.id) in teacher.get(r.headers['Location']).data.decode()
    # Unsorted
    teacher.post('/quiz/makevprob', data=dict(form, title='Later', subjects_shown='1', unsorted='1'))
    assert VProblem.query.filter_by(title='Later').one().vpgroups == []
    # a new subject typed on the form (an existing name in another case is reused)
    teacher.post('/quiz/makevprob', data=dict(form, title='Shapes', subjects_shown='1', new_subject=' Geometry '))
    teacher.post('/quiz/makevprob', data=dict(form, title='Lines', subjects_shown='1', new_subject='geometry',
                                               subjects=[str(alg.id)]))
    geo = VPGroup.query.filter_by(title='Geometry').one()
    assert VPGroup.query.count() == 2
    assert sorted(p.title for p in geo.vproblems) == ['Lines', 'Shapes']
    assert sorted(g.title for g in VProblem.query.filter_by(title='Lines').one().vpgroups) == ['Algebra', 'Geometry']
    # an overlong new name is refused before anything is saved
    r = teacher.post('/quiz/makevprob', data=dict(form, title='Long', subjects_shown='1', new_subject='x' * 65))
    assert VProblem.query.filter_by(title='Long').count() == 0 and 'at most 64 characters' in r.data.decode()

    # editing: ticks shown; unticking everything puts it in Unsorted (no question needed)
    assert 'value="{}" checked'.format(alg.id) in teacher.get('/quiz/editvprob/{}'.format(vp.id)).data.decode()
    teacher.post('/quiz/editvprob/{}'.format(vp.id), data=dict(form, subjects_shown='1'))
    db.session.expire_all()
    assert vp.vpgroups == []
    # a form without the Subjects row (e.g. the API, or an older page) leaves them alone
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [vp.id]})
    teacher.post('/quiz/editvprob/{}'.format(vp.id), data=form)
    db.session.expire_all()
    assert [g.title for g in vp.vpgroups] == ['Algebra']

    # quizzes the same way
    teacher.post('/quiz/subjects/quizzes/new', data={'name': 'Period 2'})
    p2 = VQGroup.query.one()
    r = teacher.post('/quiz/makevquiz', data={'title': 'Q', 'vplist': str(vp.id), 'subjects_shown': '1'})
    assert VQuiz.query.count() == 0 and 'Choose a subject for this quiz' in r.data.decode()
    teacher.post('/quiz/makevquiz', data={'title': 'Q', 'vplist': str(vp.id), 'subjects_shown': '1', 'subjects': [str(p2.id)]})
    vq = VQuiz.query.one()
    assert [g.title for g in vq.vqgroups] == ['Period 2']
    # problem subjects can't be given to a quiz (ids from the other list are ignored)
    teacher.post('/quiz/editvquiz/{}'.format(vq.id), data={'title': 'Q', 'vplist': str(vp.id), 'subjects_shown': '1',
                                                           'subjects': ['999']})
    db.session.expire_all()
    assert vq.vqgroups == []


def test_quiz_builder_shows_problems_in_containers(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VPGroup, VQGroup, VQuiz
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area')
    for name in ('Algebra', 'Geometry'):
        teacher.post('/quiz/subjects/problems/new', data={'name': name})
    alg, geo = (VPGroup.query.filter_by(title=n).one() for n in ('Algebra', 'Geometry'))
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id]})
    teacher.post('/quiz/subjects/problems/file', data={'subject': geo.id, 'items': [probs['Add'].id, probs['Area'].id]})
    builder = teacher.get('/quiz/makevquiz').data.decode()
    # each problem in each of its containers, with its own tick box (same value, different id)
    assert 'data-store="qgen-open-subjects-builder"' in builder and 'Rename' not in builder
    assert 'id="pick-{}-{}"'.format(alg.id, probs['Add'].id) in builder
    assert 'id="pick-{}-{}"'.format(geo.id, probs['Add'].id) in builder
    assert builder.count('class="pick" value="{}"'.format(probs['Add'].id)) == 2
    # a quiz made from problems in two subjects
    teacher.post('/quiz/makevquiz', data={'title': 'Mixed', 'vplist': '[{}, {}]'.format(probs['Add'].id, probs['Area'].id)})
    assert sorted(p.title for p in VQuiz.query.one().vproblems) == ['Add', 'Area']

    # assign: the Subject menu narrows the quizzes; a link for one quiz opens on All
    for title in ('Q1', 'Q2'):
        teacher.post('/quiz/makevquiz', data={'title': title, 'vplist': str(probs['Add'].id)})
    teacher.post('/quiz/subjects/quizzes/new', data={'name': 'Period 2'})
    p2 = VQGroup.query.one()
    q1, q2 = (VQuiz.query.filter_by(title=t).one() for t in ('Q1', 'Q2'))
    teacher.post('/quiz/subjects/quizzes/file', data={'subject': p2.id, 'items': [q2.id]})
    page = teacher.get('/quiz/assign').data.decode()
    assert 'id="assign-subject"' in page and '<option value="all" selected>' in page
    assert '"{}": [{}]'.format(q2.id, p2.id) in page and '"{}": []'.format(q1.id) in page
    assert '<option value="{}" selected>'.format(p2.id) in teacher.get('/quiz/assign?subject={}'.format(p2.id)).data.decode()
    page = teacher.get('/quiz/assign?vq={}'.format(q1.id)).data.decode()
    assert '<option value="all" selected>' in page and '<option selected value="{}">Q1</option>'.format(q1.id) in page
    sam_id = User.query.filter_by(username='sam').one().id
    teacher.post('/quiz/assign', data={'vquiz': q1.id, 'users': [sam_id]})
    assert len(q1.cquizzes) == 1
    from app.api.serialize import problem_json, vquiz_json
    assert problem_json(probs['Add'])['subjects'] == [{'id': alg.id, 'name': 'Algebra'}, {'id': geo.id, 'name': 'Geometry'}]
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
