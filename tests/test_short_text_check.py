"""Short text: an answer that isn't on the list but contains one of its answers as a whole
word ("a brown horse" for "horse") waits for the teacher to check it."""
from test_flow import app_db, login, take_page, problem_form  # noqa: F401  (fixture)


def test_grading_rule():
    from app.qgen.qtypes import get_qtype
    qt = get_qtype('text')
    for typed, credit in (('horse', 1.0), ('Horse.', 1.0), ('  HORSE ', 1.0), ('cow', 0.0), ('', 0.0),
                          ('a brown horse', None), ('horse!', None), ('seahorse', 0.0), ('horses', 0.0)):
        assert qt.grade(typed, 'horse\npony', {}, {}) == credit, typed
    assert qt.grade('a pony', 'horse\npony', {}, {}) is None
    # a labeled picture: anything but its label waits for the teacher; blank is still wrong
    pics = {'images': [{'file': 'a.png', 'label': 'dog'}, {'file': 'b.png', 'label': 'cat'}]}
    assert qt.grade('dog', 'dog', {}, pics) == 1.0 and qt.grade('spike', 'dog', {}, pics) is None
    assert qt.grade('', 'dog', {}, pics) == 0.0
    # pictures without labels: as before
    assert qt.grade('spike', 'dog', {}, {'images': [{'file': 'a.png', 'label': ''}]}) == 0.0


def test_close_answer_waits_for_the_teacher(app_db):
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.user.models import User
    teacher = login(app, 'teach')
    for f in (problem_form('text', 'Animal', 'What animal pulls a cart?', 'horse'),
              problem_form('numeric', 'Add', '2 + 2 = ?', '4')):
        assert teacher.post('/quiz/makevprob', data=f).status_code == 302
    ids = ', '.join(str(p.id) for p in VProblem.query.order_by(VProblem.id).all())
    teacher.post('/quiz/makevquiz', data={'title': 'Farm', 'vplist': ids})
    vq = VQuiz.query.one()
    sam = User.query.filter_by(username='sam').one()
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam.id]})
    s = login(app, 'sam')
    cq = CQuiz.query.one()
    take_page(s, cq.id)
    text = [cp for cp in cq.cproblems if cp.vproblem.qtype == 'text'][0]
    num = [cp for cp in cq.cproblems if cp.vproblem.qtype == 'numeric'][0]
    s.post('/quiz/take/{}'.format(cq.id), data={'Number{}'.format(text.ordinal): 'a brown horse', 'Number{}'.format(num.ordinal): '4'})
    db.session.expire_all()
    cq = db.session.get(CQuiz, cq.id)
    text = [cp for cp in cq.cproblems if cp.vproblem.qtype == 'text'][0]
    assert cq.needs_review and not cq.completed and text.credit is None and text.conc_opts['to_check']
    # on the Grading page, with the answer, the accepted answers and a credit box
    page = teacher.get('/quiz/review/{}'.format(cq.id)).data.decode()
    assert 'check this answer' in page and 'a brown horse' in page and 'Accepted answers:' in page
    r = teacher.post('/quiz/review/{}'.format(cq.id), data={'items-0-cpid': text.id, 'items-0-credit': 100,
                                                          'items-0-feedback': 'Yes, a horse.', 'finalize': 'Finish'})
    assert r.status_code == 302
    db.session.expire_all()
    cq = db.session.get(CQuiz, cq.id)
    assert cq.completed and cq.score == 100
    page = s.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'a brown horse' in page and 'Yes, a horse.' in page
