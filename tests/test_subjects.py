"""Subjects: the teacher's own lists for sorting problems and quizzes."""
from test_flow import app_db, login, problem_form, no_titles, without_all_box  # noqa: F401  (fixture)



def make_problems(teacher, *titles):
    from app.qgen.models import VProblem
    for t in titles:
        #the same question each time: "Save anyway" past the same-problem notice (same_ok)
        teacher.post('/quiz/makevprob', data=problem_form('numeric', t, 'What is 2 + 2?', '4', [], same_ok='1'))
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
    page = without_all_box(teacher.get(url + ('?folder={}'.format(folder) if folder is not None else '')).data.decode())
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


def everything(teacher, kind):
    """All titles in ?folder=all, boxes and all, in page order (a thing in two folders twice)."""
    import re
    url = '/quiz/listvp' if kind == 'problems' else '/quiz/listvq'
    page = without_all_box(teacher.get(url + '?folder=all').data.decode())
    return re.findall(r'aria-label="Check “([^”]+)”"', page[page.index('id="folder-items"'):])


def side_counts(page):
    """{name in the folder list: its count} from a page with folders down the side."""
    import re
    return {name.strip(): int(n) if n.strip() else 0 for name, n in
            re.findall(r'class="side-link"[^>]*>\s*(?:<span[^>]*>[^<]*</span>\s*)?(?:<svg\b[^>]*>.*?</svg>\s*)?(?:<span class="side-name">)?([^<]+)(?:</span>)?</a>\s*'
                       r'<span class="side-count[^"]*"[^>]*>([^<]*)</span>', page)}


def test_problems_page_lists_by_folder(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area', 'Angles')
    # no folders yet: All problems, and the same Uncategorized
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
    assert side_counts(page) == {'All problems': 3, 'Uncategorized': 0, 'Algebra': 2, 'Geometry': 2}
    assert 'Expand all' in page and 'Collapse all' in page and 'Move to folder' in page
    # taken out of a folder: it stays in its others; out of its only folder it's deleted, but
    # only once the teacher agrees (the page asks first: check=1 gives the question)
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Area'].id], 'action': 'remove'})
    assert shown(teacher, 'problems', alg.id) == ['Add'] and shown(teacher, 'problems', geo.id) == ['Angles', 'Area']
    q = teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id], 'action': 'remove', 'check': '1'},
                     headers={'X-Requested-With': 'fetch'}).get_json()
    assert q['question'].startswith('“Add” is only in “Algebra”. Do you want me to permanently delete it or put it in Uncategorized?')
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id], 'action': 'remove'})
    assert shown(teacher, 'problems', alg.id) == ['Add']  # not asked: nothing happened
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id], 'action': 'remove', 'confirm': 'uncategorized'})
    assert shown(teacher, 'problems', alg.id) == [] and shown(teacher, 'problems', 'main') == ['Add']
    # an empty folder says so
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Calculus'})
    calc = VPGroup.query.filter_by(title='Calculus').one()
    assert 'Nothing in this folder yet.' in teacher.get('/quiz/listvp?folder={}'.format(calc.id)).data.decode()
    # nothing checked, or no folder chosen: nothing happens
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id})
    teacher.post('/quiz/subjects/problems/file', data={'items': [probs['Angles'].id]})
    db.session.expire_all()
    assert [p.title for p in alg.vproblems] == []  # (Area and Add were taken out, above)
    # a folder that's gone shows All problems: one list, each once (the folder buttons narrow it)
    assert sorted(shown(teacher, 'problems', 999)) == ['Add', 'Angles', 'Area'] and sorted(everything(teacher, 'problems')) == ['Add', 'Angles', 'Area']


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
    # All quizzes: one list, each once, newest first; folder buttons (folderfilter.js) narrow it,
    # and take drops like the folder list
    assert shown(teacher, 'quizzes') == ['Q2', 'Q1'] and everything(teacher, 'quizzes') == ['Q2', 'Q1']
    page = teacher.get('/quiz/listvq?folder=all').data.decode()
    q2 = VQuiz.query.filter_by(title='Q2').one()
    assert '"keys": ["quiz:{}"]'.format(q2.id) in page and '"name": "Period 2"' in page and 'data-droppable' in page


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
    assert r.headers['Location'].endswith('/quiz/listvq?folder=all&moved=quiz:{}'.format(q.id))
    FETCH = {'X-Requested-With': 'fetch'}
    # dragged from Fall to Spring: moved
    res = teacher.post('/quiz/subjects/quizzes/move', data={'quiz': q.id, 'to': spring.id, 'from': fall.id}, headers=FETCH).get_json()
    assert res == {'ok': True, 'message': 'Moved “Q1” to “Spring”.'}
    db.session.expire_all()
    assert [g.title for g in q.vqgroups] == ['Spring']
    # dragged from All onto Fall: put in it too
    teacher.post('/quiz/subjects/quizzes/move', data={'quiz': q.id, 'to': fall.id, 'from': 'all'}, headers=FETCH)
    db.session.expire_all()
    assert sorted(g.title for g in q.vqgroups) == ['Fall', 'Spring']
    # dragged out of Fall onto Uncategorized: out of Fall only
    teacher.post('/quiz/subjects/quizzes/move', data={'quiz': q.id, 'to': 'top', 'from': fall.id}, headers=FETCH)
    db.session.expire_all()
    assert [g.title for g in q.vqgroups] == ['Spring']
    # a chip's ✕ on its only folder: deleted, but only once the teacher agrees
    res = teacher.post('/quiz/subjects/quizzes/remove', data={'quiz': q.id, 'folder': spring.id}, headers=FETCH)
    assert res.status_code == 409 and 'only in “Spring”' in res.get_json()['confirm']
    db.session.expire_all()
    assert [g.title for g in q.vqgroups] == ['Spring']
    qid = q.id
    teacher.post('/quiz/subjects/quizzes/remove', data={'quiz': qid, 'folder': spring.id, 'confirm': 'delete'})
    db.session.expire_all()
    assert db.session.get(VQuiz, qid) is None  # never taken: deleted for good
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
    # Math counts what's in Algebra too; one list of both, with a folder button for Algebra (and
    # "Math itself"); the path shows in Algebra
    assert side_counts(page)['Math'] == 2 and side_counts(page)['Algebra'] == 1
    assert '"name": "Algebra"' in page and 'data-main-label="Unsorted"' in page and sorted(shown(teacher, 'problems', math.id)) == ['Add', 'Area']
    #(the path is the heading, "Math › Algebra", with Up going back to Math)
    page = teacher.get('/quiz/listvp?folder={}'.format(alg.id)).data.decode()
    assert ' Math › Algebra</h2>' in page and 'folder-up" href="/quiz/listvp?folder={}"'.format(math.id) in page
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
    # the Quiz card's folder tabs: the quiz is under Math, and under Algebra inside it
    quiz = page[page.index('id="pick-quiz"'):page.index('id="pick-people"')]
    tree = json.loads(re.search(r'class="folder-filter-tree">(.*?)</script>', quiz, re.S).group(1))
    key = 'quiz:{}'.format(VQuiz.query.one().id)
    assert tree[0]['id'] == math.id and key in tree[0]['keys']
    assert tree[0]['children'][0]['id'] == alg.id and key in tree[0]['children'][0]['keys']
    assert 'type="radio" name="vquiz" value="{}"'.format(VQuiz.query.one().id) in quiz


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
    import re
    assert re.search(r'data-item="{}" data-box="problem:{}" [^>]*data-show'.format(vp.id, vp.id), teacher.get(r.headers['Location']).data.decode())
    # the same problem again: said once, nothing saved; "Save" again (same_ok) saves it anyway
    r = teacher.post('/quiz/makevprob', data=dict(form, title='Later', subjects_shown='1'))
    assert r.status_code == 200 and 'You already have this problem' in r.data.decode() and 'name="same_ok"' in r.data.decode()
    assert VProblem.query.count() == 1
    form['same_ok'] = '1'
    # none chosen: in no folder (Uncategorized)
    teacher.post('/quiz/makevprob', data=dict(form, title='Later', subjects_shown='1'))
    assert VProblem.query.filter_by(title='Later').one().vpgroups == []
    # a new subject typed on the form (an existing name in another case is reused)
    teacher.post('/quiz/makevprob', data=dict(form, title='Shapes', subjects_shown='1', new_subject=' Geometry '))
    #(with one folder checked, a new name now makes the folder inside that one, the owner
    #2026-10-16: see test_a_new_folder_name_taken_elsewhere_with_one_folder_checked)
    teacher.post('/quiz/makevprob', data=dict(form, title='Lines', subjects_shown='1', new_subject='geometry'))
    geo = VPGroup.query.filter_by(title='Geometry').one()
    assert VPGroup.query.count() == 2
    assert sorted(p.title for p in geo.vproblems) == ['Lines', 'Shapes']
    assert sorted(g.title for g in VProblem.query.filter_by(title='Lines').one().vpgroups) == ['Geometry']
    # one folder checked and a new name: the new folder is made inside it, with the problem in it
    teacher.post('/quiz/makevprob', data=dict(form, title='Rays', subjects_shown='1', new_subject='Lines and rays',
                                               subjects=[str(alg.id)]))
    inner = VPGroup.query.filter_by(title='Lines and rays').one()
    assert inner.parent_id == alg.id
    assert [g.title for g in VProblem.query.filter_by(title='Rays').one().vpgroups] == ['Lines and rays']
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
    # every problem once, with the folders as tabs over the list (static/js/folderfilter.js):
    # Add is in Algebra and Geometry, Area in Geometry only
    import json, re
    assert 'Rename' not in builder
    assert builder.count('class="pick" value="{}"'.format(probs['Add'].id)) == 1
    tree = json.loads(re.search(r'class="folder-filter-tree">(.*?)</script>', builder, re.S).group(1))
    keys = {t['name']: t['keys'] for t in tree}
    assert keys == {'Algebra': ['p:{}'.format(probs['Add'].id)],
                    'Geometry': sorted(['p:{}'.format(probs['Add'].id), 'p:{}'.format(probs['Area'].id)])}
    assert 'data-all-label="All problems"' in builder and 'data-fkey="p:{}"'.format(probs['Area'].id) in builder
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
    import json, re
    def quiz_card(url):
        page = teacher.get(url).data.decode()
        return page[page.index('id="pick-quiz"'):page.index('id="pick-people"')]
    # Assign's Quiz card: folder tabs over the quizzes, starting on All quizzes
    card = quiz_card('/quiz/assign')
    assert 'data-start="all"' in card
    tree = json.loads(re.search(r'class="folder-filter-tree">(.*?)</script>', card, re.S).group(1))
    assert tree[0]['id'] == p2.id and tree[0]['keys'] == ['quiz:{}'.format(q2.id)]  # Q1 is in no folder
    # ?subject= opens on that folder's tab; a link for one quiz opens on its own folder (or
    # Uncategorized, "none", when it's in none) with it picked
    assert 'data-start="{}"'.format(p2.id) in quiz_card('/quiz/assign?subject={}'.format(p2.id))
    card = quiz_card('/quiz/assign?vq={}'.format(q1.id))
    assert 'data-start="none"' in card and 'value="{}" id="vquiz-{}" checked'.format(q1.id, q1.id) in card
    card = quiz_card('/quiz/assign?vq={}'.format(q2.id))
    assert 'data-start="{}"'.format(p2.id) in card and 'value="{}" id="vquiz-{}" checked'.format(q2.id, q2.id) in card
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
    #(no Answer column and no "Question and answer" icon: View shows the question and its answer, the
    #owner 2026-10-21)
    from app.qgen.models import VProblem
    sky = VProblem.query.filter_by(title='Sky').one()
    assert 'data-qa=' not in page
    view = teacher.get('/quiz/viewvprob/{}'.format(sky.id)).data.decode()
    assert 'Why is the sky blue?' in view and 'Light scatters.' in view
    # one People page (no Accounts | Results switch: the owner, 2026-10-21): its people are rows that open
    # to show their results (they were boxes: the owner, 2026-10-21)
    results = no_titles(teacher.get('/userdet').data.decode())
    assert '>Results</a>' not in results and '>Accounts</a>' not in results and 'people_switch' not in results
    assert teacher.get('/quiz/listuser').headers['Location'] == '/userdet'
    assert '<tr class="result-item" data-box="user:' in results and '<details class="box row-fold" data-box="user-row:' in results
    assert '<div class="result-groups divided" data-fold-body>' in results
    assert 'data-level="open"' in results and 'js/folders.js' in results and 'class="state-filter"' in results


def test_they_are_called_folders_on_screen(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    make_problems(teacher, 'Add')
    page = teacher.get('/quiz/listvp').data.decode()
    assert '+ New folder' in page and 'Make a folder first' in page
    r = teacher.post('/quiz/subjects/problems/new', data={'name': 'Algebra'}, follow_redirects=True)
    assert 'Folder “Algebra” made.' in r.data.decode()
    page = teacher.get('/quiz/listvp').data.decode()
    #(each row's own way into a folder is now its Move to folder icon, not a "+" menu)
    assert 'Move to folder' in page and 'Take out of folder' in page and 'title="Move to folder: move “Add” to a folder' in page
    from app.qgen.models import VPGroup
    page = teacher.get('/quiz/listvp?folder={}'.format(VPGroup.query.one().id)).data.decode()
    assert 'Delete the folder “Algebra”? Nothing in it is deleted' in page and 'Folder options' in page
    r = teacher.post('/quiz/subjects/problems/new', data={'name': 'algebra'}, follow_redirects=True)
    assert 'There&#39;s already a folder called' in r.data.decode()
    form = teacher.get('/quiz/makevprob').data.decode()
    assert '<legend>Folder' in form and 'Or a new folder' in form
    for url in ('/quiz/listvp', '/quiz/listvq', '/quiz/makevprob', '/quiz/makevquiz', '/quiz/assign'):
        text = teacher.get(url).data.decode()
        assert '>Subject' not in text and 'subject “' not in text and 'New subject' not in text, url


def test_a_new_folder_name_taken_elsewhere_with_one_folder_checked(app_db):
    """A new folder's name that's already a folder somewhere else, with one folder checked (so
    it would be made inside that one): the teacher is told, not shown a server error, and the
    problem isn't saved half-filed."""
    app, db = app_db
    from app.qgen.models import VPGroup, VProblem
    teacher = login(app, 'teach')
    for name in ('Algebra', 'Geometry'):
        teacher.post('/quiz/subjects/problems/new', data={'name': name})
    alg = VPGroup.query.filter_by(title='Algebra').one()
    form = problem_form('numeric', 'Lines', 'What is 2 + 2?', '4', [])
    r = teacher.post('/quiz/makevprob', data=dict(form, subjects_shown='1', new_subject='geometry', subjects=[str(alg.id)]))
    assert r.status_code in (200, 302)
    if r.status_code == 200:
        assert 'already a folder called' in r.data.decode() and VProblem.query.count() == 0


def test_the_quiz_builder_says_what_students_get(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    page = teacher.get('/quiz/makevquiz').data.decode()
    assert '<h2>Problems in this quiz</h2>' in page and 'id="order-total"' in page
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
    # nested tabs: L4 inside L3, inside L2, inside L1, each holding P4
    import json, re
    tree = json.loads(re.search(r'class="folder-filter-tree">(.*?)</script>', html, re.S).group(1))
    node = tree[0]
    for g in chain:
        assert node['id'] == g.id and 'p:{}'.format(probs['P4'].id) in node['keys']
        node = node['children'][0] if node['children'] else None
    assert html.count('class="pick" value="{}"'.format(probs['P4'].id)) == 1


def test_coming_back_to_a_folder_page_keeps_the_folder_tab_open(app_db):
    """The open folder tab (?tab=, folderfilter.js) survives an edit and Save, and a folder action
    done on that page; a fresh visit (the menus' links) has no tab and starts on All."""
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Math'})
    math = VPGroup.query.one()
    listed = 'http://localhost/quiz/listvp?tab={}'.format(math.id)
    # every folder page's own list keeps its tab in the address
    assert 'data-url-tab' in teacher.get('/quiz/listvp').data.decode()
    # Save in the editor opened from the Math tab: back to the list on that tab, the problem lit up
    form = problem_form('numeric', 'Add', 'What is 3 + 3?', '6', [], next='/quiz/listvp?tab={}'.format(math.id))
    r = teacher.post('/quiz/editvprob/{}'.format(probs['Add'].id), data=form)
    assert r.status_code == 302 and r.headers['Location'] == '/quiz/listvp?tab={}&show={}'.format(math.id, probs['Add'].id)
    # ...and the list's filter words and an old highlight: the words stay, the old highlight goes
    form['next'] = '/quiz/listvp?tab={}&q=add&show=999'.format(math.id)
    r = teacher.post('/quiz/editvprob/{}'.format(probs['Add'].id), data=form)
    assert r.headers['Location'] == '/quiz/listvp?tab={}&q=add&show={}'.format(math.id, probs['Add'].id)
    # opened with no tab (or from somewhere else): the list as before
    form['next'] = ''
    r = teacher.post('/quiz/editvprob/{}'.format(probs['Add'].id), data=form)
    assert r.headers['Location'] == '/quiz/listvp?show={}'.format(probs['Add'].id)
    # a folder action from the page (a new folder) comes back to the same tab
    r = teacher.post('/quiz/subjects/problems/new', data={'name': 'Other', 'view': 'all'}, headers={'Referer': listed})
    assert 'tab={}'.format(math.id) in r.headers['Location']
    # ...but not when the action opens another view
    r = teacher.post('/quiz/subjects/problems/new', data={'name': 'Third', 'view': 'all'}, headers={'Referer': 'http://localhost/quiz/listvp'})
    assert 'tab=' not in r.headers['Location']


def test_deleting_or_making_something_comes_back_to_the_list_as_it_was(app_db):
    """Delete (back_to_list): the list it was done on, its tab and filter kept, its one-time
    highlights (?show=, ?moved=) dropped; from anywhere else (or another site), the plain list.
    A new problem always comes back to the list, on the tab it was started from."""
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area', 'Sum')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Math'})
    math = VPGroup.query.one()
    page = 'http://localhost/quiz/listvp?tab={}&q=a&show=7&moved=3'.format(math.id)
    r = teacher.post('/quiz/delvp/{}'.format(probs['Add'].id), headers={'Referer': page})
    assert r.headers['Location'] == '/quiz/listvp?tab={}&q=a'.format(math.id)
    r = teacher.post('/quiz/delvp/{}'.format(probs['Area'].id), headers={'Referer': 'https://elsewhere.example/quiz/listvp?tab=1'})
    assert r.headers['Location'] == '/quiz/listvp'
    r = teacher.post('/quiz/delvp/{}'.format(probs['Sum'].id), headers={'Referer': 'http://localhost/dashboard'})
    assert r.headers['Location'] == '/quiz/listvp'
    # a new problem started from the Math tab comes back there; started from the Dashboard, to the list
    from app.qgen.models import VProblem
    form = problem_form('numeric', 'New one', 'What is 1 + 1?', '2', [], next='/quiz/listvp?tab={}'.format(math.id))
    r = teacher.post('/quiz/makevprob', data=form)
    new = VProblem.query.filter_by(title='New one').one()
    assert r.headers['Location'] == '/quiz/listvp?tab={}&show={}'.format(math.id, new.id)
    form = problem_form('numeric', 'Another', 'What is 2 + 2?', '4', [], next='/dashboard')
    r = teacher.post('/quiz/makevprob', data=form)
    assert r.headers['Location'].startswith('/quiz/listvp?show=')


def test_an_archive_folder_action_keeps_the_open_tab(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    r = teacher.post('/quiz/archive/folders/new', data={'name': 'Old', 'view': 'all'},
                     headers={'Referer': 'http://localhost/quiz/archive?tab=none'})
    assert 'tab=none' in r.headers['Location']


def test_with_no_folders_uncategorized_counts_everything_and_opens(app_db):
    """No folders yet: Uncategorized counts what's in no folder, everything (the owner, 2026-10-19),
    and isn't grayed: a tab with something in it always opens (the owner, 2026-10-20)."""
    app, db = app_db
    teacher = login(app, 'teach')
    make_problems(teacher, 'Add', 'Area')
    page = teacher.get('/quiz/listvp').data.decode()
    at = page.index('title="See the problems that aren’t in any folder"')
    #(pinned with the automatic folders at the top now: the owner, 2026-10-21)
    row = page[page.rindex('<li class="side-auto" data-auto="none">', 0, at):page.index('</div></li>', at)]
    assert 'is-empty' not in row and '>2</span>' in row
    assert 'There are no folders yet' not in page
    import os
    assert 'There are no folders yet' not in open(os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'folderfilter.js')).read()


def test_each_folder_page_keeps_its_own_filter_and_tab_in_the_address(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    make_problems(teacher, *['P{}'.format(i) for i in range(7)])
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Math'})
    page = teacher.get('/quiz/listvp').data.decode()
    assert page.count('data-url-filter') == 1 and 'data-url-tab' in page


def test_a_student_page_keeps_its_folder_tab_in_the_address(app_db):
    app, db = app_db
    from test_dashboard import make_quiz, give
    from app.user.models import User
    teacher = login(app, 'teach')
    give(make_quiz(app, teacher), 'sam')
    sam = User.query.filter_by(username='sam').one()
    page = teacher.get('/quiz/listuser/{}'.format(sam.id)).data.decode()
    assert 'data-remember="student-page" data-url-tab' in page and 'data-url-filter' in page


def test_cards_that_pick_from_folders_show_a_folder_list_down_their_side(app_db):
    """Assign's Quiz and Students cards, the quiz builder's Problems and a student's page: the
    folders as a list down the card's side (data-style="list"), Expand all / Collapse all on the
    filter bar (data-tools-home); When, with the Assign button, after the Quiz card."""
    app, db = app_db
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add')
    teacher.post('/quiz/makevquiz', data={'title': 'Q1', 'vplist': str(probs['Add'].id)})
    page = teacher.get('/quiz/assign').data.decode()
    #(the Messages side panel's "write to" picker, on every page, is a third such list)
    assert 'data-remember="write-to" data-tools-home="#write-to-bar" data-style="list"' in page
    assert page.count('data-style="list"') == 3
    assert 'data-tools-home="#quiz-filter-bar" data-style="list"' in page and 'data-tools-home="#people-pick-bar" data-style="list"' in page
    assert page.index('id="pick-quiz"') < page.index('id="pick-people"') < page.index('class="card assign-when"') < page.index('class="assign-go"')
    assert 'data-tools-home="#problem-filter-bar" data-style="list"' in teacher.get('/quiz/makevquiz').data.decode()


def test_assign_with_no_quizzes_says_so_and_a_removed_quizs_link_picks_the_first(app_db):
    app, db = app_db
    from datetime import datetime
    from app.qgen.models import VQuiz
    teacher = login(app, 'teach')
    page = teacher.get('/quiz/assign').data.decode()
    quiz = page[page.index('id="pick-quiz"'):page.index('id="pick-people"')]
    assert 'No quizzes yet.' in quiz and '/quiz/makevquiz' in quiz and 'folder-filter' not in quiz
    probs = make_problems(teacher, 'Add')
    for title in ('A quiz', 'B quiz'):
        teacher.post('/quiz/makevquiz', data={'title': title, 'vplist': str(probs['Add'].id)})
    a, b = VQuiz.query.filter_by(title='A quiz').one(), VQuiz.query.filter_by(title='B quiz').one()
    b.removed_at = datetime.now()
    db.session.commit()
    # a link to a removed quiz: it isn't offered, so the first quiz is checked, as with no link
    page = teacher.get('/quiz/assign?vq={}'.format(b.id)).data.decode()
    assert 'value="{}" id="vquiz-{}" checked'.format(a.id, a.id) in page
    assert 'vquiz-{}'.format(b.id) not in page


def test_the_folder_question_folds_like_the_folder_lists(app_db):
    """The Folder question on the problem form: a fold arrow on a folder with folders inside,
    Expand all / Collapse all above the list, and each folder's count."""
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    make_problems(teacher, 'Add')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Math'})
    math = VPGroup.query.filter_by(title='Math').one()
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Algebra', 'parent': math.id})
    page = teacher.get('/quiz/makevprob').data.decode()
    q = page[page.index('id="subject-question"'):page.index('</fieldset>', page.index('id="subject-question"'))]
    assert q.count('class="side-fold"') == 1 and 'aria-label="Show or hide the folders in Math"' in q
    assert 'data-side-level="open"' in q and 'data-side-level="close"' in q and 'js/folder_checks.js' in q
    assert 'data-depth="2" data-folder="{}"'.format(VPGroup.query.filter_by(title='Algebra').one().id) in q



def test_out_of_its_only_folder_asks_delete_or_uncategorized(app_db):
    """Every folder page: taking something out says where it's still in; out of its only folder
    it's asked first, and then deleted for good (or put in Uncategorized), as chosen."""
    app, db = app_db
    from app.qgen.models import VPGroup, VProblem
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area')
    for name in ('Algebra', 'Geometry'):
        teacher.post('/quiz/subjects/problems/new', data={'name': name})
    alg, geo = VPGroup.query.filter_by(title='Algebra').one(), VPGroup.query.filter_by(title='Geometry').one()
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id, probs['Area'].id]})
    teacher.post('/quiz/subjects/problems/file', data={'subject': geo.id, 'items': [probs['Area'].id]})
    FETCH = {'X-Requested-With': 'fetch'}
    # a card's Take out (the new route for every kind): Area stays in Geometry, and says so
    res = teacher.post('/folders/problems/takeout', data={'items': [probs['Area'].id], 'folder': alg.id}, headers=FETCH).get_json()
    assert res['message'] == 'Took “Area” out of “Algebra”; it’s still in “Geometry”.'
    # Add is only in Algebra: asked, nothing changes until the teacher chooses
    res = teacher.post('/folders/problems/takeout', data={'items': [probs['Add'].id], 'folder': alg.id}, headers=FETCH)
    assert res.status_code == 409 and res.get_json()['confirm'] == \
        '“Add” is only in “Algebra”. Do you want me to permanently delete it or put it in Uncategorized?'
    assert VProblem.query.filter_by(title='Add').count() == 1
    res = teacher.post('/folders/problems/takeout', data={'items': [probs['Add'].id], 'folder': alg.id, 'confirm': 'delete'}, headers=FETCH)
    assert res.get_json()['message'] == 'Deleted problem “Add”.' and VProblem.query.filter_by(title='Add').count() == 0
    # a problem a quiz uses: Delete for good keeps it for the quiz, quietly off the Problems page
    teacher.post('/quiz/makevquiz', data={'title': 'Q', 'vplist': str(probs['Area'].id)})
    teacher.post('/folders/problems/takeout', data={'items': [probs['Area'].id], 'folder': geo.id, 'confirm': 'delete'})
    db.session.expire_all()
    area = VProblem.query.filter_by(title='Area').one()
    assert area.removed_at is not None and area.vpgroups == [] and '>Area<' not in teacher.get('/quiz/listvp').data.decode()
    from app.qgen.models import VQuiz
    assert 'Area' in teacher.get('/quiz/editvquiz/{}'.format(VQuiz.query.filter_by(title='Q').one().id)).data.decode()  # the quiz keeps it
    # students can't
    assert login(app, 'sam').post('/folders/problems/takeout', data={'items': [probs['Area'].id], 'folder': geo.id}).status_code == 302


def test_the_checked_bars_take_out_asks_the_forms_own_address():
    """The checked bar's buttons are named "action", which hides form.action in the browser:
    "Take out of folder" asked nowhere and did nothing (Quizzes, Problems, People)."""
    import os, re
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(here, 'static', 'js', 'takeout.js')).read()
    assert "fetchJson(form.getAttribute('action')" in js
    assert not re.search(r'\bform\.action\b(?!")', js.replace('form.action:', '').replace('hides form.action', ''))
    for t in ('app/qgen/templates/_folder_tools.html', 'app/user/templates/udet.html'):
        html = open(os.path.join(here, t)).read()
        assert 'data-takeout="remove"' in html and 'name="action" value="remove"' in html


def test_deleting_a_folder_says_what_moved_where(app_db):
    """Deleting a folder (its things move up a level): the message names them and where they went."""
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Math'})
    math = VPGroup.query.filter_by(title='Math').one()
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Algebra', 'parent': math.id})
    alg = VPGroup.query.filter_by(title='Algebra').one()
    teacher.post('/quiz/subjects/problems/file', data={'subject': alg.id, 'items': [probs['Add'].id]})
    teacher.post('/quiz/subjects/problems/file', data={'subject': math.id, 'items': [probs['Area'].id]})
    r = teacher.post('/quiz/subjects/problems/{}/delete'.format(alg.id), follow_redirects=True).data.decode()
    assert 'Deleted the folder “Algebra”. Moved to “Math” (its Unsorted): “Add”.' in r
    r = teacher.post('/quiz/subjects/problems/{}/delete'.format(math.id), follow_redirects=True).data.decode()
    assert 'Deleted the folder “Math”. Moved to Uncategorized: “Add”, “Area”.' in r
    # the delete question says where things go, and the folder tabs carry the Folder options
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Science'})
    page = teacher.get('/quiz/listvp').data.decode()
    assert 'Delete the folder “Science”? Nothing in it is deleted: the problems in it move up to Uncategorized.' in page
    assert 'class="folder-filter-tools"' in page and 'Folder options' in page


def test_back_up_to_the_outer_folder_says_where_else_it_is(app_db):
    """Out of a folder inside another, it goes back to the outer one (its Unsorted), and the
    message also names the other folders it's still in (the owner, 2026-10-14)."""
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add')
    for name in ('Outer', 'Top'):
        teacher.post('/quiz/subjects/problems/new', data={'name': name})
    outer = VPGroup.query.filter_by(title='Outer').one()
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Inner', 'parent': outer.id})
    inner, top = VPGroup.query.filter_by(title='Inner').one(), VPGroup.query.filter_by(title='Top').one()
    for g in (inner, top):
        teacher.post('/quiz/subjects/problems/file', data={'subject': g.id, 'items': [probs['Add'].id]})
    res = teacher.post('/folders/problems/takeout', data={'items': [probs['Add'].id], 'folder': inner.id, 'just': '1'},
                       headers={'X-Requested-With': 'fetch'}).get_json()
    assert res['message'] == 'Took “Add” out of “Inner”; it’s now in “Outer” (its Unsorted) and still in “Top”.'
    db.session.expire_all()
    assert sorted(g.title for g in db.session.get(type(probs['Add']), probs['Add'].id).vpgroups) == ['Outer', 'Top']
    # (the trash can no longer carries each folder's outer folders: nothing read them, the code
    # critic 2026-10-20; the message above names them, from the server)
    page = teacher.get('/quiz/listvp').data.decode()
    assert 'data-chains=' not in page and 'data-remove-one' in page
