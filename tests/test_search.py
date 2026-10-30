"""Search Everything…, beside each folder page's filter box: every folder, names and what's inside, shown as a folder view
of its own, "Search: “x”"; Clear Search goes back to the folder you were in (the owner, 2026-10-29, To do 76)."""
from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)
from test_assign_pages import ids, quiz_of


def test_problems_found_by_question_text_and_note_from_any_folder(app_db):
    from app.qgen.models import VProblem
    app, db = app_db
    teacher = login(app, 'teach')
    vq, probs = quiz_of(teacher, 'S1', 'S2')
    p = db.session.get(VProblem, probs[1].id)
    p.teacher_note = 'needs a picture of zebras'
    db.session.commit()
    page = teacher.get('/quiz/listvp?folder=main&search=zebras').data.decode()
    assert 'Search: “zebras”' in page and '>S2<' in page and '>S1<' not in page
    #(Clear Search: the same address without the search, back to the folder it came from)
    assert 'href="/quiz/listvp?folder=main" title="Clear Search' in page
    #(the question text counts: every problem here says "What is [a] + [b]?")
    assert '>S1<' in teacher.get('/quiz/listvp?search=what is').data.decode()
    assert 'Nothing matches “nope-nothing”.' in teacher.get('/quiz/listvp?search=nope-nothing').data.decode()


def test_people_found_by_email(app_db):
    from app.user.models import User
    app, db = app_db
    teacher = login(app, 'teach')
    u = db.session.get(User, ids('kim'))
    u.email = 'kim.marsh@school.test'
    db.session.commit()
    page = teacher.get('/userdet?search=marsh').data.decode()
    assert 'Search: “marsh”' in page and 'data-box="user:{}"'.format(ids('kim')) in page
    assert 'data-box="user:{}"'.format(ids('sam')) not in page


def test_every_folder_page_has_the_box(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    vq, _ = quiz_of(teacher, 'S3')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    for url in ('/quiz/listvp', '/quiz/listvq', '/userdet', '/quiz/open', '/quiz/listuser/{}'.format(ids('sam'))):
        page = teacher.get(url).data.decode()
        assert 'placeholder="Search Everything…"' in page and '>Search</button>' in page, url
    page = teacher.get('/quiz/open?search=S3').data.decode()
    assert 'Search: “S3”' in page and 'Q S3' in page
    history = teacher.get('/quiz/listuser/{}?search=S3'.format(ids('sam'))).data.decode()
    assert 'Search: \\u201cS3\\u201d' in history or 'Search: “S3”' in history


def test_problems_open_row_shows_one_students_version(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    quiz_of(teacher, 'P9')
    page = teacher.get('/quiz/listvp?search=P9').data.decode()
    assert 'class="problem-peek small"' in page and 'What is ' in page and '[a]' not in page.split('problem-peek')[1][:400]
