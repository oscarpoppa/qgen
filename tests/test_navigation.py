"""Finding your way: pages named by what they show, Back buttons that say where they go,
one name per action, and the student page's quiz boxes."""
import re

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_dashboard import make_quiz, give
from test_archive import ids


def test_clear_page_names_and_back_buttons(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, 'Week 1')
    cq = give(vq, 'sam')
    title = lambda page: re.search(r'<title>([^<]*)</title>', page).group(1)
    # names, not numbers
    # one quiz's old address: its row on Quizzes, lit up (the one-row page is gone)
    assert teach.get('/quiz/listvq/{}'.format(vq.id)).headers['Location'] == '/quiz/listvq?show={}'.format(vq.id)
    assert title(teach.get('/quiz/listcq/{}'.format(cq.id)).data.decode()).startswith("Answer key: sam – Week 1")
    assert title(teach.get('/edituser/{}'.format(ids('sam'))).data.decode()).startswith('Edit user: sam')
    assert title(app.test_client().get('/login').data.decode()).startswith('Log in')
    # the way back is the top bar's arrows (worded Back buttons removed)
    from test_flow import back_by_the_trail
    assert back_by_the_trail(teach.get('/quiz/listcq/{}'.format(cq.id)).data.decode())
    # one name per action: Grading in the menu
    assert '">Grading' in teach.get('/dashboard').data.decode()
    # the student page: each quiz a row that folds, like My quizzes' (the owner, 2026-10-21; they were boxes)
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert '<tr class="row-is-new" data-fkey="q:{}" data-name="week 1"'.format(vq.id) in page
    #(one student's page is laid out like the other list pages: its folder list's levels get
    #Expand all / Collapse all from folderfilter.js)
    assert 'data-folder-filter' in page and 'aria-label="Not started"' in page
    # Results by student (everyone, on People now: the owner, 2026-10-21) keeps its table
    assert 'class="card result-box"' not in teach.get('/userdet').data.decode()


def test_the_count_beside_a_name_is_quizzes_not_attempts(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    w1, w2 = make_quiz(app, teach, 'Week 1'), make_quiz(app, teach, 'Week 2')
    for _ in range(5):
        give(w1, 'sam')  # one quiz, five attempts
    give(w2, 'sam')
    #(People's Quizzes column: Results by student is the People page now, the owner 2026-10-21)
    page = teach.get('/userdet').data.decode()
    assert '<td data-label="Quizzes" class="nowrap" data-sort="0002"><span class="badge box-count" title="2 quizzes" aria-label="2 quizzes">2</span></td>' in page
    #(one student's page has no box round the student: its New folder counts quizzes too)
    import json
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    tree = json.loads(re.search(r'class="folder-filter-tree">(.*?)</script>', page, re.S).group(1))
    assert [(t['id'], t['count']) for t in tree if t['id'] == 'new'] == [('new', 2)]
    assert page.count('data-fkey="q:') == 2
