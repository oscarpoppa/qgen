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
    # Back says where it goes
    assert "← sam&#39;s student page</a>" in teach.get('/quiz/listcq/{}'.format(cq.id)).data.decode()
    # one name per action: Grading in the menu
    assert '">Grading' in teach.get('/dashboard').data.decode()
    # the student page: each quiz a box that folds
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert 'class="box card result-box quiz-is-new" data-list data-quiz-box="{}-{}">'.format(ids('sam'), vq.id) in page
    assert 'data-level="open" data-level-of="#student-' in page and '<span class="badge">Not started</span>' in page
    # Results by student (everyone) keeps its table
    assert 'class="card result-box"' not in teach.get('/quiz/listuser').data.decode()


def test_the_count_beside_a_name_is_quizzes_not_attempts(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    w1, w2 = make_quiz(app, teach, 'Week 1'), make_quiz(app, teach, 'Week 2')
    for _ in range(5):
        give(w1, 'sam')  # one quiz, five attempts
    give(w2, 'sam')
    for url in ('/quiz/listuser', '/quiz/listuser/{}'.format(ids('sam'))):
        page = teach.get(url).data.decode()
        assert '<span class="badge box-count">2 quizzes</span>' in page, url
