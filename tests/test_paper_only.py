"""Paper only problems: done on a printed page, scored by the teacher, printed when assigned."""
from test_flow import app_db, login, take_page, png_bytes, problem_form, no_titles  # noqa: F401  (fixture)


def _picture(teacher):
    body = teacher.post('/upload/json', data={'file': (png_bytes('green'), 'shapes.png')},
                        content_type='multipart/form-data').get_json()
    assert body['ok'], body
    return body['name']


def _quiz(app, db, teacher, with_paper=True):
    from app.qgen.models import VProblem, VQuiz
    pic = _picture(teacher)
    forms = [problem_form('numeric', 'Add', '[a] + 2 = ?', 'a + 2', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}])]
    if with_paper:
        forms.append(problem_form('paper', 'Color', 'Color the triangles red.', 'All 3 triangles red',
                                  images=[{'file': pic, 'label': ''}]))
    for f in forms:
        r = teacher.post('/quiz/makevprob', data=f)
        assert r.status_code == 302, r.data.decode()[:800]
    ids = ', '.join(str(p.id) for p in VProblem.query.order_by(VProblem.id).all())
    assert teacher.post('/quiz/makevquiz', data={'title': 'Shapes', 'vplist': ids}).status_code == 302
    return VQuiz.query.filter_by(title='Shapes').one(), pic


def test_paper_only_needs_a_picture(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    r = teacher.post('/quiz/makevprob', data=problem_form('paper', 'Color', 'Color the triangles red.'))
    assert r.status_code == 200 and b'needs its page in the picture section' in r.data
    # it's on the editor's list of question kinds, with its tip
    page = teacher.get('/quiz/makevprob').data.decode()
    assert 'value="paper"' in page and 'Paper only' in page
    # for Paper only the Pictures card becomes "The page to print" (problem_form.js), and Random values hides
    assert 'id="pictures-card"' in page and 'data-paper="📄 The page to print"' in page
    assert 'class="card t-numeric t-text t-choice_one t-choice_many t-truefalse t-essay"' in page


def test_take_grade_and_print(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz
    from app.user.models import User
    teacher = login(app, 'teach')
    vq, pic = _quiz(app, db, teacher)
    sam, kim = User.query.filter_by(username='sam').one(), User.query.filter_by(username='kim').one()

    # assigning sends the teacher to print a copy for each student, then back
    r = teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam.id, kim.id], 'next': '/quiz/results/{}'.format(vq.id)})
    assert r.status_code == 302 and '/quiz/print/{}'.format(vq.id) in r.headers['Location']
    page = teacher.get(r.headers['Location']).data.decode()
    assert page.count('class="paper-sheet"') == 2
    assert 'sam' in page and 'kim' in page and 'Color the triangles red.' in page and pic in page
    assert 'window.print()' in page
    assert 'href="/quiz/results/{}"'.format(vq.id) in no_titles(page)
    # and from the quiz's results later
    assert '🖨 Print paper pages' in teacher.get('/quiz/results/{}'.format(vq.id)).data.decode()
    # students can't open it
    s = login(app, 'sam')
    assert s.get('/quiz/print/{}'.format(vq.id)).status_code == 302

    # the take page: no answer box for it, just the note; it counts as answered
    cq = CQuiz.query.filter_by(assignee=sam.id).one()
    page = take_page(s, cq.id).data.decode()
    assert 'Do this one on paper. Your teacher will check it.' in page and 'data-paper' in page
    paper = [cp for cp in cq.cproblems if cp.vproblem.qtype == 'paper'][0]
    num = [cp for cp in cq.cproblems if cp.vproblem.qtype == 'numeric'][0]
    import re
    box = re.search(r'<input[^>]*name="Number{}"[^>]*>'.format(paper.ordinal), page).group(0)
    assert 'type="hidden"' in box
    # handed in with the paper one "blank": it still waits for the teacher's score
    r = s.post('/quiz/take/{}'.format(cq.id), data={'Number{}'.format(num.ordinal): num.conc_ansr})
    assert r.status_code == 302
    db.session.expire_all()
    cq = db.session.get(CQuiz, cq.id)
    assert cq.needs_review and not cq.completed

    # the teacher scores it from the paper
    page = teacher.get('/quiz/review/{}'.format(cq.id)).data.decode()
    assert 'Done on paper. Score it from' in page and 'All 3 triangles red' in page and 'Answer key' in page
    r = teacher.post('/quiz/review/{}'.format(cq.id), data={'items-0-cpid': paper.id, 'items-0-credit': 50, 'finalize': 'Finish'})
    db.session.expire_all()
    cq = db.session.get(CQuiz, cq.id)
    assert cq.completed and abs(cq.score - 75) < 0.01
    page = s.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'Done on paper.' in page


def test_assign_message_links_to_the_quiz_and_its_results(app_db):
    app, db = app_db
    from app.user.models import User
    teacher = login(app, 'teach')
    vq, _ = _quiz(app, db, teacher, with_paper=False)
    sam = User.query.filter_by(username='sam').one()
    page = teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam.id]}, follow_redirects=True).data.decode()
    assert '<a href="/quiz/viewvquiz/{}">View the quiz</a> · <a href="/quiz/results/{}">See its results →</a>'.format(vq.id, vq.id) in page


def test_new_and_started_quizzes_have_gold_and_blue_borders(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz
    from app.user.models import User
    teacher = login(app, 'teach')
    vq, _ = _quiz(app, db, teacher, with_paper=False)
    sam = User.query.filter_by(username='sam').one()
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam.id]})
    s = login(app, 'sam')
    assert 'quiz-card quiz-is-new' in s.get('/mypage').data.decode()
    assert 'class="quiz-is-new"' in s.get('/home').data.decode()
    assert 'result-box quiz-is-new' in teacher.get('/quiz/listuser/{}'.format(sam.id)).data.decode()
    take_page(s, CQuiz.query.one().id)
    assert 'quiz-card quiz-is-started' in s.get('/mypage').data.decode()
    assert 'class="quiz-is-started"' in s.get('/home').data.decode()
    assert 'result-box quiz-is-started' in teacher.get('/quiz/listuser/{}'.format(sam.id)).data.decode()


def test_quiz_without_paper_redirects_as_before(app_db):
    app, db = app_db
    from app.user.models import User
    teacher = login(app, 'teach')
    vq, _ = _quiz(app, db, teacher, with_paper=False)
    sam = User.query.filter_by(username='sam').one()
    r = teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam.id]})
    assert r.status_code == 302 and '/quiz/print' not in r.headers['Location']
    assert '🖨 Print paper pages' not in teacher.get('/quiz/results/{}'.format(vq.id)).data.decode()
