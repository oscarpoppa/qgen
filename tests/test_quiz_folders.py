"""Folders on each person's own My quizzes page: make, rename, remove, nest, and move
quizzes and folders into them (by the "Move to" list or by dragging)."""
from test_flow import app_db, login  # noqa: F401  (fixture)
from test_archive import ids
from test_dashboard import make_quiz

FETCH = {'X-Requested-With': 'fetch'}


def assign(teacher, vq, *names):
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids(n) for n in names]})


def folder_id(name, owner):
    from app.qgen.models import QuizFolder
    return QuizFolder.query.filter_by(name=name, owner_id=ids(owner)).one().id


def cards(c, view=None):
    """The quiz boxes My quizzes shows: everything, or one part of the folder list."""
    import re
    page = c.get('/mypage' + ('?folder={}'.format(view) if view is not None else '')).data.decode()
    return re.findall(r'<h2 title="([^"]+)">', page)


def test_make_folders_and_put_quizzes_in_them(app_db):
    app, db = app_db
    teach, sam, kim = login(app, 'teach'), login(app, 'sam'), login(app, 'kim')
    w1, w2 = make_quiz(app, teach, 'Week 1'), make_quiz(app, teach, 'Week 2')
    assign(teach, w1, 'sam', 'kim')
    assign(teach, w2, 'sam')
    page = sam.get('/mypage').data.decode()
    assert '+ New folder' in page and 'class="move-form"' not in page  # no folders yet: nothing to move to
    r = sam.post('/mypage/folders', data={'name': '  Unit   1 '}, follow_redirects=True)
    assert 'Folder &#34;Unit 1&#34; made.' in r.data.decode() or 'Folder "Unit 1" made.' in r.data.decode()
    unit = folder_id('Unit 1', 'sam')
    page = sam.get('/mypage').data.decode()
    assert page.count('aria-label="Move Week 1 to a folder"') == 1 and '📁 Unit 1</option>' in page
    # the Move to list
    assert sam.post('/mypage/move', data={'quiz': w1.id, 'to': unit}, headers=FETCH).get_json() == \
        {'ok': True, 'message': 'Moved "Week 1" to "Unit 1".'}
    # a quiz is in one place only: the folder shows it, and the main list doesn't any more
    assert cards(sam, unit) == ['Week 1'] and cards(sam) == ['Week 2']
    page = sam.get('/mypage').data.decode()
    assert 'aria-current="page"><span aria-hidden="true">📚</span> Main list' in page
    assert cards(sam, 'none') == ['Week 2']  # an old address: the main list
    # All quizzes: every one, each saying its folder
    all_page = sam.get('/mypage?folder=all').data.decode()
    assert sorted(cards(sam, 'all')) == ['Week 1', 'Week 2'] and '📁 Unit 1</a></p>' in all_page
    assert 'aria-current="page"><span aria-hidden="true">🗂️</span> All quizzes' in all_page
    import re
    assert re.search(r'aria-current="page">\s*<span aria-hidden="true">📁</span> <span class="side-name">Unit 1',
                     sam.get('/mypage?folder={}'.format(unit)).data.decode())
    # a folder that isn't theirs (or is gone) shows the main list
    assert cards(kim, unit) == ['Week 1']
    # only for sam: kim's page and folders are her own
    assert 'Unit 1' not in kim.get('/mypage').data.decode()
    assert kim.post('/mypage/move', data={'quiz': w1.id, 'to': unit}, headers=FETCH).status_code == 400
    assert kim.post('/mypage/folders/{}/rename'.format(unit), data={'name': 'x'}, headers=FETCH).status_code == 400
    assert kim.post('/mypage/folders/{}/delete'.format(unit), data={}, headers=FETCH).status_code == 400
    # a quiz that isn't yours can't be filed
    assert kim.post('/mypage/folders', data={'name': 'K'}, headers=FETCH).get_json()['ok']
    assert kim.post('/mypage/move', data={'quiz': w2.id, 'to': folder_id('K', 'kim')}, headers=FETCH).get_json() == \
        {'ok': False, 'error': 'That quiz isn\'t on your list.'}
    # back to the main list
    assert sam.post('/mypage/move', data={'quiz': w1.id, 'to': 'top'}, headers=FETCH).get_json()['message'] == 'Moved "Week 1" to the main list.'
    assert cards(sam, unit) == [] and 'No quizzes in this folder' in sam.get('/mypage?folder={}'.format(unit)).data.decode()
    # names: needed, not too long; renaming
    assert sam.post('/mypage/folders', data={'name': '   '}, headers=FETCH).get_json()['error'] == 'Please give the folder a name.'
    assert not sam.post('/mypage/folders', data={'name': 'x' * 65}, headers=FETCH).get_json()['ok']
    assert sam.post('/mypage/folders/{}/rename'.format(unit), data={'name': 'Unit One'}, headers=FETCH).get_json()['ok']
    assert '<span class="side-name">Unit One</span>' in sam.get('/mypage').data.decode()


def test_folders_inside_folders_and_removing_them(app_db):
    app, db = app_db
    from app.qgen.models import QuizFolder, QuizPlacement
    teach, sam = login(app, 'teach'), login(app, 'sam')
    w1 = make_quiz(app, teach, 'Week 1')
    assign(teach, w1, 'sam')
    sam.post('/mypage/folders', data={'name': 'Math'})
    sam.post('/mypage/folders', data={'name': 'Algebra', 'parent': folder_id('Math', 'sam')})
    math, algebra = folder_id('Math', 'sam'), folder_id('Algebra', 'sam')
    sam.post('/mypage/move', data={'quiz': w1.id, 'to': algebra})
    assert cards(sam, algebra) == ['Week 1'] and cards(sam, math) == ['Week 1']  # in Algebra's box
    page = sam.get('/mypage?folder={}'.format(math)).data.decode()
    assert '+ New folder inside' in page and 'No quizzes in this folder itself' in page
    assert '<details class="sub-box" data-sub="{}">'.format(algebra) in page
    page = sam.get('/mypage?folder={}'.format(algebra)).data.decode()
    assert '<a href="/mypage?folder={}">Math</a>'.format(math) in page  # Math › Algebra
    # a folder can't go inside itself, or inside a folder in it
    assert sam.post('/mypage/move', data={'folder': math, 'to': algebra}, headers=FETCH).get_json()['error'] == \
        'A folder can\'t go inside itself.'
    assert not sam.post('/mypage/move', data={'folder': math, 'to': math}, headers=FETCH).get_json()['ok']
    # moving a folder (dragging it out to the main list)
    assert sam.post('/mypage/move', data={'folder': algebra, 'to': 'top'}, headers=FETCH).get_json()['message'] == \
        'Moved "Algebra" to the top level.'
    assert db.session.get(QuizFolder, algebra).parent_id is None
    sam.post('/mypage/move', data={'folder': algebra, 'to': math})
    # removing Math: Algebra (with the quiz) moves up to the main list; no quiz is deleted
    assert sam.post('/mypage/folders/{}/delete'.format(math), data={}, headers=FETCH).get_json()['ok']
    assert db.session.get(QuizFolder, math) is None and db.session.get(QuizFolder, algebra).parent_id is None
    assert QuizPlacement.query.filter_by(owner_id=ids('sam')).one().folder_id == algebra
    # removing Algebra: the quiz is back in the main list
    sam.post('/mypage/folders/{}/delete'.format(algebra), data={})
    assert QuizPlacement.query.count() == 0
    assert 'title="Week 1"' in sam.get('/mypage').data.decode()
    # a removed folder's quiz goes to its parent folder
    sam.post('/mypage/folders', data={'name': 'A'})
    sam.post('/mypage/folders', data={'name': 'B', 'parent': folder_id('A', 'sam')})
    sam.post('/mypage/move', data={'quiz': w1.id, 'to': folder_id('B', 'sam')})
    sam.post('/mypage/folders/{}/delete'.format(folder_id('B', 'sam')), data={})
    assert QuizPlacement.query.one().folder_id == folder_id('A', 'sam')


def test_how_deep_folders_go(app_db):
    app, db = app_db
    from app.qgen import folders
    sam = login(app, 'sam')
    parent = None
    for n in range(folders.MAX_DEPTH):
        r = sam.post('/mypage/folders', data={'name': 'L{}'.format(n), 'parent': parent or ''}, headers=FETCH).get_json()
        assert r['ok'], r
        parent = folder_id('L{}'.format(n), 'sam')
    assert sam.post('/mypage/folders', data={'name': 'too deep', 'parent': parent}, headers=FETCH).get_json()['error'] == \
        'Folders can go only {} levels deep.'.format(folders.MAX_DEPTH)
    # nor by moving a folder with folders in it under another
    sam.post('/mypage/folders', data={'name': 'X'})
    sam.post('/mypage/folders', data={'name': 'Y', 'parent': folder_id('X', 'sam')})
    assert not sam.post('/mypage/move', data={'folder': folder_id('X', 'sam'), 'to': folder_id('L4', 'sam')},
                        headers=FETCH).get_json()['ok']
    assert sam.post('/mypage/move', data={'folder': folder_id('X', 'sam'), 'to': folder_id('L3', 'sam')},
                    headers=FETCH).get_json()['ok']


def test_folders_need_the_page_token_and_go_with_the_account(app_db):
    app, db = app_db
    from app.qgen.models import QuizFolder, QuizPlacement
    teach, sam = login(app, 'teach'), login(app, 'sam')
    w1 = make_quiz(app, teach, 'Week 1')
    assign(teach, w1, 'sam')
    sam.post('/mypage/folders', data={'name': 'Mine'})
    sam.post('/mypage/move', data={'quiz': w1.id, 'to': folder_id('Mine', 'sam')})
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        sam.post('/mypage/folders', data={'name': 'Forged'})
        assert QuizFolder.query.filter_by(name='Forged').count() == 0
    finally:
        app.config['WTF_CSRF_ENABLED'] = False
    assert app.test_client().post('/mypage/folders', data={'name': 'anon'}).status_code == 302
    # a teacher's own My quizzes has folders too
    assert teach.post('/mypage/folders', data={'name': 'Try-outs'}, headers=FETCH).get_json()['ok']
    # the account's folders go with it
    from app.user.models import User
    db.session.delete(db.session.get(User, ids('sam')))
    db.session.commit()
    assert QuizFolder.query.filter_by(name='Mine').count() == 0 and QuizPlacement.query.count() == 0


def test_after_a_change_the_same_folder_shows(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    w1 = make_quiz(app, teach, 'Week 1')
    assign(teach, w1, 'sam')
    r = sam.post('/mypage/folders', data={'name': 'Unit 1', 'view': 'all'})
    unit = folder_id('Unit 1', 'sam')
    assert r.headers['Location'].endswith('/mypage?folder=all')  # you stay where you were
    r = sam.post('/mypage/move', data={'quiz': w1.id, 'to': unit, 'view': 'main'})
    assert r.headers['Location'].endswith('/mypage')  # stays where you were
    r = sam.post('/mypage/folders/{}/rename'.format(unit), data={'name': 'U1', 'view': str(unit)})
    assert r.headers['Location'].endswith('/mypage?folder={}'.format(unit))
    sam.post('/mypage/folders', data={'name': 'Inner', 'parent': unit})
    inner = folder_id('Inner', 'sam')
    # removing the folder you're looking at: its parent shows (or the main list)
    assert sam.post('/mypage/folders/{}/delete'.format(inner), data={'view': str(inner)}).headers['Location'] \
        .endswith('/mypage?folder={}'.format(unit))
    assert sam.post('/mypage/folders/{}/delete'.format(unit), data={'view': str(unit)}).headers['Location'] \
        .endswith('/mypage')
    assert cards(sam) == ['Week 1']


def test_a_retake_brings_the_quiz_out_of_its_folder(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, QuizPlacement
    teach, sam, kim = login(app, 'teach'), login(app, 'sam'), login(app, 'kim')
    w1 = make_quiz(app, teach, 'Week 1')
    assign(teach, w1, 'sam', 'kim')
    for c, name in ((sam, 'sam'), (kim, 'kim')):
        c.post('/mypage/folders', data={'name': 'Done'})
        c.post('/mypage/move', data={'quiz': w1.id, 'to': folder_id('Done', name)})
    cq = CQuiz.query.filter_by(assignee=ids('sam')).one()
    from app.qgen import services as S
    S.submit(cq, {})
    r = teach.post('/quiz/retcq/{}'.format(cq.id), data={})
    assert r.status_code in (200, 302)
    assert CQuiz.query.filter_by(assignee=ids('sam')).count() == 2
    # sam's is back out of the folder; kim's stays put; the folder itself stays
    assert cards(sam) == ['Week 1'] and cards(sam, folder_id('Done', 'sam')) == []
    assert QuizPlacement.query.filter_by(owner_id=ids('kim')).count() == 1


def test_folders_inside_show_as_boxes_with_their_own_expand_and_collapse(app_db):
    app, db = app_db
    import re
    teach, sam = login(app, 'teach'), login(app, 'sam')
    w1, w2 = make_quiz(app, teach, 'Week 1'), make_quiz(app, teach, 'Week 2')
    assign(teach, w1, 'sam')
    assign(teach, w2, 'sam')
    sam.post('/mypage/folders', data={'name': 'Math'})
    math = folder_id('Math', 'sam')
    sam.post('/mypage/folders', data={'name': 'Algebra', 'parent': math})
    algebra = folder_id('Algebra', 'sam')
    sam.post('/mypage/move', data={'quiz': w1.id, 'to': math})
    sam.post('/mypage/move', data={'quiz': w2.id, 'to': algebra})
    page = sam.get('/mypage?folder={}'.format(math)).data.decode()
    # Math's own quiz, and Algebra as a box holding its quiz
    assert re.findall(r'<h2 title="([^"]+)">', page) == ['Week 2', 'Week 1']
    assert '<details class="sub-box" data-sub="{}">'.format(algebra) in page
    assert page.index('data-sub="{}"'.format(algebra)) < page.index('title="Week 2"') < page.index('title="Week 1"')
    # Expand all / Collapse all for Math, and for Algebra's box
    assert page.count('data-level="open"') == 2 and 'aria-label="Collapse all in Algebra"' in page
    assert 'aria-label="Expand all in Math"' in page
    # Algebra's box: drop a quiz on its title to move it in
    assert '<summary class="sub-head" data-drop="{}">'.format(algebra) in page
