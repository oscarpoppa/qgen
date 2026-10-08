"""Subjects: the teacher's own lists for sorting problems and quizzes."""
from test_flow import app_db, login, problem_form, no_titles  # noqa: F401  (fixture)



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


def shown(teacher, kind, folder='all'):
    """The titles listed on the Problems (or Quizzes) page for ?folder=, outside folder boxes."""
    import re
    url = '/quiz/listvp' if kind == 'problems' else '/quiz/listvq'
    page = teacher.get(url + ('?folder={}'.format(folder) if folder is not None else '')).data.decode()
    items = page[page.index('id="folder-items"'):] if 'id="folder-items"' in page else ''
    #folder boxes (details.sub-box) are skipped: what's in them is listed in their own view
    while '<details class="box sub-box"' in items:
        start = items.index('<details class="box sub-box"')
        depth, i = 0, start
        while True:
            o, c = items.find('<details', i), items.find('</details>', i)
            if o != -1 and o < c:
                depth, i = depth + 1, o + 8
            else:
                depth, i = depth - 1, c + 10
                if depth == 0:
                    break
        items = items[:start] + items[i:]
    return re.findall(r'aria-label="Check “([^”]+)”"', items)


def side_counts(page):
    """{name in the folder list: its count} from a page with folders down the side."""
    import re
    return {name.strip(): int(n) if n.strip() else 0 for name, n in
            re.findall(r'class="side-link"[^>]*>\s*(?:<span[^>]*>[^<]*</span>\s*)?(?:<span class="side-name">)?([^<]+)(?:</span>)?</a>\s*'
                       r'<span class="side-count[^"]*"[^>]*>([^<]*)</span>', page)}


def test_problems_page_lists_by_folder(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area', 'Angles')
    # no folders yet: All problems, and the same Not in a folder
    assert shown(teacher, 'problems') == ['Angles', 'Area', 'Add']
    assert shown(teacher, 'problems', 'main') == ['Angles', 'Area', 'Add']
    for name in ('Geometry', 'Algebra'):
        teacher.post('/quiz/subjects/problems/new', data={'name': name})
    alg, geo = (VPGroup.query.filter_by(title=n).one() for n in ('Algebra', 'Geometry'))

    # checked rows: put in, again (harmless), and a problem in two folders
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id, probs['Area'].id]})
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id], 'action': 'add'})
    teacher.post('/quiz/subjects/problems/file', data={'subject': geo.id, 'items': [probs['Area'].id, probs['Angles'].id]})
    assert shown(teacher, 'problems', alg.id) == ['Area', 'Add'] and shown(teacher, 'problems', geo.id) == ['Angles', 'Area']
    assert shown(teacher, 'problems', 'main') == []
    page = teacher.get('/quiz/listvp').data.decode()
    assert side_counts(page) == {'All problems': 3, 'Not in a folder': 0, 'Algebra': 2, 'Geometry': 2}
    assert 'Expand all' in page and 'Collapse all' in page and 'Put in folder' in page
    # taken out of a folder: in no folder if it's in no other
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id], 'action': 'remove'})
    assert shown(teacher, 'problems', alg.id) == ['Area'] and shown(teacher, 'problems', 'main') == ['Add']
    # an empty folder says so
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Calculus'})
    calc = VPGroup.query.filter_by(title='Calculus').one()
    assert 'Nothing in this folder yet.' in teacher.get('/quiz/listvp?folder={}'.format(calc.id)).data.decode()
    # nothing checked, or no folder chosen: nothing happens
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id})
    teacher.post('/quiz/subjects/problems/file', data={'items': [probs['Angles'].id]})
    db.session.expire_all()
    assert [p.title for p in alg.vproblems] == ['Area']
    # a folder that's gone shows All problems
    assert shown(teacher, 'problems', 999) == ['Angles', 'Area', 'Add']


def test_quizzes_page_lists_by_folder(app_db):
    app, db = app_db
    from app.qgen.models import VQGroup, VQuiz
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add')
    for t in ('Q1', 'Q2'):
        teacher.post('/quiz/makevquiz', data={'title': t, 'vplist': str(probs['Add'].id)})
    teacher.post('/quiz/subjects/quizzes/new', data={'name': 'Period 2'})
    p2 = VQGroup.query.one()
    teacher.post('/quiz/subjects/quizzes/file', data={'subject': p2.id, 'items': [VQuiz.query.filter_by(title='Q2').one().id]})
    assert shown(teacher, 'quizzes', p2.id) == ['Q2'] and shown(teacher, 'quizzes', 'main') == ['Q1']
    assert shown(teacher, 'quizzes') == ['Q2', 'Q1']


def test_one_at_a_time_and_dragging(app_db):
    app, db = app_db
    from app.qgen.models import VQGroup, VQuiz
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add')
    teacher.post('/quiz/makevquiz', data={'title': 'Q1', 'vplist': str(probs['Add'].id)})
    q = VQuiz.query.one()
    for name in ('Fall', 'Spring'):
        teacher.post('/quiz/subjects/quizzes/new', data={'name': name})
    fall, spring = (VQGroup.query.filter_by(title=n).one() for n in ('Fall', 'Spring'))
    # "+ Add…": stays where it was, lit up after
    r = teacher.post('/quiz/subjects/quizzes/add', data={'quiz': q.id, 'to': fall.id, 'view': 'all'})
    assert r.headers['Location'].endswith('/quiz/listvq?moved=quiz:{}'.format(q.id))
    FETCH = {'X-Requested-With': 'fetch'}
    # dragged from Fall to Spring: moved
    res = teacher.post('/quiz/subjects/quizzes/move', data={'quiz': q.id, 'to': spring.id, 'from': fall.id}, headers=FETCH).get_json()
    assert res == {'ok': True, 'message': 'Moved "Q1" to "Spring".'}
    db.session.expire_all()
    assert [g.title for g in q.vqgroups] == ['Spring']
    # dragged from All onto Fall: put in it too
    teacher.post('/quiz/subjects/quizzes/move', data={'quiz': q.id, 'to': fall.id, 'from': 'all'}, headers=FETCH)
    db.session.expire_all()
    assert sorted(g.title for g in q.vqgroups) == ['Fall', 'Spring']
    # dragged out of Fall onto Not in a folder: out of Fall only
    teacher.post('/quiz/subjects/quizzes/move', data={'quiz': q.id, 'to': 'top', 'from': fall.id}, headers=FETCH)
    db.session.expire_all()
    assert [g.title for g in q.vqgroups] == ['Spring']
    # a chip's ✕
    teacher.post('/quiz/subjects/quizzes/remove', data={'quiz': q.id, 'folder': spring.id})
    db.session.expire_all()
    assert q.vqgroups == []
    # a quiz that's gone
    res = teacher.post('/quiz/subjects/quizzes/move', data={'quiz': 999, 'to': fall.id}, headers=FETCH)
    assert res.status_code == 400 and 'doesn\'t exist' in res.get_json()['error']


def test_folders_inside_folders(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Math'})
    math = VPGroup.query.one()
    r = teacher.post('/quiz/subjects/problems/new', data={'name': 'Algebra', 'parent': math.id, 'view': math.id})
    assert r.headers['Location'].endswith('/quiz/listvp?folder={}'.format(math.id))  # stays where it was
    alg = VPGroup.query.filter_by(title='Algebra').one()
    assert alg.parent_id == math.id
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id]})
    teacher.post('/quiz/subjects/problems/file', data={'subject': math.id, 'items': [probs['Area'].id]})
    page = teacher.get('/quiz/listvp?folder={}'.format(math.id)).data.decode()
    # Math counts what's in Algebra too; Algebra is a box inside it; the path shows in Algebra
    assert side_counts(page)['Math'] == 2 and side_counts(page)['Algebra'] == 1
    assert '<details class="box sub-box" data-sub="{}" data-list>'.format(alg.id) in page and shown(teacher, 'problems', math.id) == ['Area']
    assert '>Math</a> <span class="muted" aria-hidden="true">›</span>' in teacher.get('/quiz/listvp?folder={}'.format(alg.id)).data.decode()
    # never inside itself
    FETCH = {'X-Requested-With': 'fetch'}
    res = teacher.post('/quiz/subjects/problems/move', data={'folder': math.id, 'to': alg.id}, headers=FETCH)
    assert res.status_code == 400 and 'inside itself' in res.get_json()['error']
    # the Assign page's and the forms' lists show it under Math
    teacher.post('/quiz/subjects/problems/move', data={'folder': alg.id, 'to': 'top'}, headers=FETCH)
    db.session.expire_all()
    assert db.session.get(VPGroup, alg.id).parent_id is None
    teacher.post('/quiz/subjects/problems/move', data={'folder': alg.id, 'to': math.id}, headers=FETCH)
    # removing Math: Algebra and Area move up to the top; nothing is deleted
    teacher.post('/quiz/subjects/problems/{}/delete'.format(math.id), data={'view': math.id})
    db.session.expire_all()
    assert db.session.get(VPGroup, math.id) is None and db.session.get(VPGroup, alg.id).parent_id is None
    assert shown(teacher, 'problems', 'main') == ['Area'] and shown(teacher, 'problems', alg.id) == ['Add']
    # removing a folder inside another: what's in it moves into that one
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Math'})
    math = VPGroup.query.filter_by(title='Math').one()
    teacher.post('/quiz/subjects/problems/move', data={'folder': alg.id, 'to': math.id}, headers=FETCH)
    teacher.post('/quiz/subjects/problems/{}/delete'.format(alg.id))
    assert shown(teacher, 'problems', math.id) == ['Add']


def test_quiz_in_a_folder_inside_another_is_under_both_on_assign(app_db):
    app, db = app_db
    from app.qgen.models import VQGroup, VQuiz
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add')
    teacher.post('/quiz/makevquiz', data={'title': 'Q1', 'vplist': str(probs['Add'].id)})
    teacher.post('/quiz/subjects/quizzes/new', data={'name': 'Math'})
    math = VQGroup.query.one()
    teacher.post('/quiz/subjects/quizzes/new', data={'name': 'Algebra', 'parent': math.id})
    alg = VQGroup.query.filter_by(title='Algebra').one()
    teacher.post('/quiz/subjects/quizzes/file', data={'subject': alg.id, 'items': [VQuiz.query.one().id]})
    page = teacher.get('/quiz/assign').data.decode()
    import json, re
    mapping = json.loads(re.search(r'id="quiz-subjects">([^<]*)</script>', page).group(1))
    assert sorted(mapping[str(VQuiz.query.one().id)]) == sorted([math.id, alg.id])
    assert '\u00a0\u00a0\u00a0Algebra (1)' in page and 'Not in a folder (0)' in page


def test_new_items_can_be_given_a_subject(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup, VQGroup, VProblem, VQuiz
    teacher = login(app, 'teach')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Algebra'})
    alg = VPGroup.query.one()
    form = problem_form('numeric', 'Filed', 'What is 2 + 2?', '4', [])
    page = teacher.get('/quiz/makevprob').data.decode()
    assert '(optional)' in page and 'name="new_subject"' in page

    # a subject: saved in it, and the list opens where it is
    r = teacher.post('/quiz/makevprob', data=dict(form, subjects_shown='1', subjects=[str(alg.id)]))
    vp = VProblem.query.one()
    assert [g.title for g in vp.vpgroups] == ['Algebra']
    assert r.headers['Location'].endswith('/quiz/listvp?show={}'.format(vp.id))
    assert 'data-item="{}" data-box="problem:{}" data-show'.format(vp.id, vp.id) in teacher.get(r.headers['Location']).data.decode()
    # none chosen: in no folder (Not in a folder)
    teacher.post('/quiz/makevprob', data=dict(form, title='Later', subjects_shown='1'))
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

    # editing: checks shown; unchecking everything puts it in Unsorted (no question needed)
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
    # each problem in each of its containers, with its own checkbox (same value, different id)
    assert 'Rename' not in builder
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
    assert problem_json(probs['Add'])['labels'] == [{'id': alg.id, 'name': 'Algebra'}, {'id': geo.id, 'name': 'Geometry'}]
    assert vquiz_json(q2)['labels'] == [{'id': p2.id, 'name': 'Period 2'}]


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


def test_written_answers_say_teacher_graded_and_pages_link_up(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('essay', 'Summer', 'Write about your summer.'))
    teacher.post('/quiz/makevprob', data=problem_form('essay', 'Sky', 'Why is the sky blue?', 'Light scatters.'))
    make_problems(teacher, 'Add')
    page = teacher.get('/quiz/listvp').data.decode()
    assert page.count('<span class="badge">Teacher-graded</span>') == 2
    assert 'Model answer: Light scatters.' in page
    # the Users page links to Results by student, whose students are boxes that open and close
    assert 'href="/quiz/listuser">Results by student</a>' in no_titles(teacher.get('/userdet').data.decode())
    results = teacher.get('/quiz/listuser').data.decode()
    assert '<details class="box card subject-box student item-box"' in results
    assert 'data-level="open"' in results and 'js/folders.js' in results and 'class="state-filter"' in results


def test_they_are_called_folders_on_screen(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    make_problems(teacher, 'Add')
    page = teacher.get('/quiz/listvp').data.decode()
    assert '+ New folder' in page and 'Make a folder first' in page
    r = teacher.post('/quiz/subjects/problems/new', data={'name': 'Algebra'}, follow_redirects=True)
    assert 'Folder &#34;Algebra&#34; made.' in r.data.decode() or 'Folder "Algebra" made.' in r.data.decode()
    page = teacher.get('/quiz/listvp').data.decode()
    assert 'Put in folder' in page and 'Take out of folder' in page and '<option value="">+ Add…</option>' in page
    from app.qgen.models import VPGroup
    page = teacher.get('/quiz/listvp?folder={}'.format(VPGroup.query.one().id)).data.decode()
    assert 'Remove the folder “Algebra”? Nothing in it is deleted' in page and 'Folder options' in page
    r = teacher.post('/quiz/subjects/problems/new', data={'name': 'algebra'}, follow_redirects=True)
    assert 'There&#39;s already a folder called' in r.data.decode()
    form = teacher.get('/quiz/makevprob').data.decode()
    assert '<legend>Folder' in form and 'Or a new folder' in form
    for url in ('/quiz/listvp', '/quiz/listvq', '/quiz/makevprob', '/quiz/makevquiz', '/quiz/assign'):
        text = teacher.get(url).data.decode()
        assert '>Subject' not in text and 'subject “' not in text and 'New subject' not in text, url


def test_the_quiz_builder_says_what_students_get(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    page = teacher.get('/quiz/makevquiz').data.decode()
    assert '<h2>Questions in this quiz</h2>' in page and 'id="order-total"' in page
    assert 'Want each student to get only some of these?' in page
    assert 'Order in the quiz' not in page and 'shuffle-note' not in page


def test_folders_four_deep_show_on_folder_pages_and_in_the_quiz_editor(app_db):
    """A folder in a folder in a folder in a folder: the Problems page and the quiz editor draw
    every level (each a standard folder box inside the one it's in), with its problems."""
    app, db = app_db
    teacher = login(app, 'teach')
    from app.qgen.models import VPGroup
    probs = make_problems(teacher, 'P1', 'P2', 'P3', 'P4')
    parent, chain = None, []
    for name in ('L1', 'L2', 'L3', 'L4'):
        g = VPGroup(title=name, parent_id=parent)
        db.session.add(g)
        db.session.flush()
        chain.append(g)
        parent = g.id
    for g, p in zip(chain, probs.values()):
        g.vproblems.append(p)
    db.session.commit()
    page = teacher.get('/quiz/listvp?folder={}'.format(chain[0].id))
    assert page.status_code == 200
    builder = teacher.get('/quiz/makevquiz')
    assert builder.status_code == 200
    html = builder.data.decode()
    for g in chain:
        assert '<details class="box sub-box" data-sub="{}" data-list>'.format(g.id) in html
    # nested: L4's box is inside L3's, inside L2's, inside L1's
    starts = [html.index('data-sub="{}"'.format(g.id)) for g in chain]
    assert starts == sorted(starts) and html.index('class="box-title">L4</h3>') < html.index('</details>', starts[3])
    assert html.count('class="pick" value="{}"'.format(probs['P4'].id)) == 1
