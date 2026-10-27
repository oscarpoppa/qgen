"""Delete grayed (and refused) while something still uses it (the owner, 2026-10-26, To do 65): a picture or file a
problem or quiz uses; a quiz someone is taking right now."""
import os
from datetime import datetime

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_dashboard import make_quiz, give


def put_picture(name):
    from PIL import Image
    d = os.environ['STATIC_DIR'].rstrip('/') + '/'
    Image.new('RGB', (8, 8)).save(d + name)
    Image.new('RGB', (4, 4)).save(d + 'T_' + name)
    return d


def test_a_picture_in_use_cant_be_deleted(app_db):
    app, db = app_db
    from app.qgen import services as S
    teach = login(app, 'teach')
    d = put_picture('cat.png')
    put_picture('dog.png')
    vq = make_quiz(app, teach, 'Week 2')
    vq.image = 'cat.png'
    vp = vq.vproblems[0]
    vp.options = dict(vp.options, images=[{'file': 'cat.png', 'label': ''}])
    db.session.commit()
    with app.test_request_context():
        why = S.file_delete_blocker('cat.png', 'pictures')
        assert why == 'Picture “cat.png” is used by these problems: “{}”; and these quizzes: “Week 2”. Take it out of them first.'.format(vp.title)
        assert S.file_delete_blocker('dog.png', 'pictures') is None
    page = teach.get('/images').data.decode()
    assert why.replace('“', '&#8220;') in page or why in page  # the grayed Delete's tooltip
    # the server refuses too; an unused one goes
    teach.post('/delimg/cat.png')
    assert os.path.exists(d + 'cat.png')
    teach.post('/delimg/dog.png')
    assert not os.path.exists(d + 'dog.png')


def test_a_quiz_being_taken_has_its_trash_grayed(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, 'Week 3')
    cq = give(vq, 'sam')
    page = teach.get('/quiz/listvq').data.decode()
    assert 'taking “Week 3” right now' not in page
    cq.startdate = datetime.now()
    cq.taker.last_seen = datetime.now()  # (active lately: "Still taking a quiz for", 2 hours)
    db.session.commit()
    page = teach.get('/quiz/listvq').data.decode()
    assert 'is taking “Week 3” right now. Try again once it’s handed in (or its time runs out).' in page


def test_a_problem_a_quiz_uses_has_its_trash_grayed_and_names_the_quiz(app_db):
    """A problem a quiz uses: its trash can grayed, naming the quizzes; the server refuses both Move to Trash and
    Delete; its opened row links to each quiz on Quizzes (the owner, 2026-10-26)."""
    app, db = app_db
    from app.qgen.models import VProblem
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, 'Week 4')
    vp = vq.vproblems[0]
    page = teach.get('/quiz/listvp').data.decode()
    why = 'Problem “{}” is used by these quizzes: “Week 4”. Take it out of them first.'.format(vp.title)
    assert why in page
    assert 'In quizzes: <a class="pick-chip row-quiz-chip" href="/quiz/listvq/{}"'.format(vq.id) in page
    teach.post('/quiz/archivevp/{}'.format(vp.id))
    teach.post('/quiz/delvp/{}'.format(vp.id))
    db.session.expire_all()
    vp = db.session.get(VProblem, vp.id)
    assert vp is not None and vp.removed_at is None


def test_a_quiz_can_take_its_own_problems_with_it(app_db):
    """Moving a quiz to the Trash, or deleting it, can take the problems no other quiz uses with it (a check box,
    checked to start); a problem another quiz uses stays (the owner, 2026-10-26)."""
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz
    teach = login(app, 'teach')
    from app.qgen import services as S
    from test_flow import problem_form
    a = make_quiz(app, teach, 'Week A')
    teach.post('/quiz/makevprob', data=problem_form('numeric', 'Shared one', 'What is 3 + 3?', '6', []))
    sh = VProblem.query.filter_by(title='Shared one').one()
    teach.post('/quiz/makevquiz', data={'title': 'Week B', 'vplist': str(sh.id), 'keep_order': 'y'})
    b = VQuiz.query.filter_by(title='Week B').one()
    own, shared = a.vproblems[0], b.vproblems[0]
    assert own.id != shared.id
    a.vproblems.append(shared)
    db.session.commit()
    assert [p.id for p in S.own_problems(a)] == [own.id]
    page = teach.get('/quiz/listvq').data.decode()
    assert 'data-own-problems="1"' in page  # (Week A: its own one; the shared one doesn't count)
    teach.post('/quiz/archivevq/{}'.format(a.id), data={'problems': '1'})
    db.session.expire_all()
    assert db.session.get(VProblem, own.id).removed_at is not None
    assert db.session.get(VProblem, shared.id).removed_at is None
    # left unchecked: the problems stay
    teach.post('/quiz/makevprob', data=problem_form('numeric', 'Keep one', 'What is 4 + 4?', '8', []))
    keep = VProblem.query.filter_by(title='Keep one').one()
    teach.post('/quiz/makevquiz', data={'title': 'Week C', 'vplist': str(keep.id), 'keep_order': 'y'})
    c = VQuiz.query.filter_by(title='Week C').one()
    teach.post('/quiz/archivevq/{}'.format(c.id))
    db.session.expire_all()
    assert db.session.get(VProblem, keep.id).removed_at is None
    # deleted for good (no one took it): its own problem deleted too
    teach.post('/quiz/makevprob', data=problem_form('numeric', 'Gone one', 'What is 5 + 5?', '10', []))
    gone_id = VProblem.query.filter_by(title='Gone one').one().id
    teach.post('/quiz/makevquiz', data={'title': 'Week D', 'vplist': str(gone_id), 'keep_order': 'y'})
    d = VQuiz.query.filter_by(title='Week D').one()
    teach.post('/quiz/delvq/{}'.format(d.id), data={'problems': '1'})
    db.session.expire_all()
    assert db.session.get(VQuiz, d.id) is None and db.session.get(VProblem, gone_id) is None
    # deleted from Quizzes but a student took it: the quiz goes to the Trash, and its own problem with it, its folders
    # kept, not deleted (the critic, 2026-10-26)
    from test_dashboard import give
    teach.post('/quiz/subjects/problems', data={'name': 'Unit 9'})
    teach.post('/quiz/makevprob', data=problem_form('numeric', 'Taken one', 'What is 6 + 6?', '12', []))
    taken = VProblem.query.filter_by(title='Taken one').one()
    S.file_one('problems', taken.id, S.subject_named('problems', 'Unit 9'))
    db.session.commit()
    teach.post('/quiz/makevquiz', data={'title': 'Week E', 'vplist': str(taken.id), 'keep_order': 'y'})
    e = VQuiz.query.filter_by(title='Week E').one()
    with app.test_request_context():
        S.submit(give(e, 'sam'), {1: '12'})
        db.session.commit()
    r = teach.post('/quiz/delvq/{}'.format(e.id), data={'problems': '1'}, follow_redirects=True).data.decode()
    db.session.expire_all()
    p = db.session.get(VProblem, taken.id)
    assert db.session.get(VQuiz, e.id).removed_at is not None
    assert p is not None and p.removed_at is not None and [g.title for g in p.vpgroups] == ['Unit 9']
    assert 'Its 1 problem went to the Trash too.' in r
    assert r.index('Removed “Week E” from Quizzes') < r.index('Its 1 problem went to the Trash too.')  # (the action first)
