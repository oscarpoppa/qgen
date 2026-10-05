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


def page_order(c, *titles):
    """Where each quiz title or folder name first appears on My quizzes."""
    page = c.get('/mypage').data.decode()
    return [page.index('title="{}"'.format(t)) for t in titles]


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
        {'ok': True, 'message': 'Moved to "Unit 1".'}
    folder_at, week1_at, week2_at = page_order(sam, 'Unit 1', 'Week 1', 'Week 2')
    assert folder_at < week1_at < week2_at  # Week 1 is inside the folder, which comes first
    assert '1 quiz<' in sam.get('/mypage').data.decode()
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
    assert sam.post('/mypage/move', data={'quiz': w1.id, 'to': 'top'}, headers=FETCH).get_json()['message'] == 'Moved to the main list.'
    assert '0 quizzes<' in sam.get('/mypage').data.decode()
    # names: needed, not too long; renaming
    assert sam.post('/mypage/folders', data={'name': '   '}, headers=FETCH).get_json()['error'] == 'Please give the folder a name.'
    assert not sam.post('/mypage/folders', data={'name': 'x' * 65}, headers=FETCH).get_json()['ok']
    assert sam.post('/mypage/folders/{}/rename'.format(unit), data={'name': 'Unit One'}, headers=FETCH).get_json()['ok']
    assert 'title="Unit One"' in sam.get('/mypage').data.decode()


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
    math_at, algebra_at, week_at = page_order(sam, 'Math', 'Algebra', 'Week 1')
    assert math_at < algebra_at < week_at
    page = sam.get('/mypage').data.decode()
    assert '+ New folder inside' in page
    # a folder can't go inside itself, or inside a folder in it
    assert sam.post('/mypage/move', data={'folder': math, 'to': algebra}, headers=FETCH).get_json()['error'] == \
        'A folder can\'t go inside itself.'
    assert not sam.post('/mypage/move', data={'folder': math, 'to': math}, headers=FETCH).get_json()['ok']
    # moving a folder (dragging it out to the main list)
    assert sam.post('/mypage/move', data={'folder': algebra, 'to': 'top'}, headers=FETCH).get_json()['ok']
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
