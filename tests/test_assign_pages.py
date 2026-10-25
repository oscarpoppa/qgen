"""The Assign quizzes page's choices, the Add to quizzes page and the stash's checked scans (the owner,
2026-10-24): what the pages send, done on the server."""
import json

from test_flow import app_db, login, problem_form, AB  # noqa: F401  (fixture)


def ids(name):
    from app.user.models import User
    return User.query.filter_by(username=name).one().id


def quiz_of(teacher, *titles, keep='y'):
    """A quiz of numeric problems with random values, one per title (in that order)."""
    from app.qgen.models import VProblem, VQuiz
    made = []
    for t in titles:
        teacher.post('/quiz/makevprob', data=problem_form('numeric', t, 'What is [a] + [b]?', 'a + b', AB, same_ok='1'))
        made.append(VProblem.query.filter_by(title=t).one())
    teacher.post('/quiz/makevquiz', data={'title': 'Q ' + titles[0], 'vplist': ','.join(str(p.id) for p in made), 'keep_order': keep})
    return VQuiz.query.filter_by(title='Q ' + titles[0]).one(), made


def copies(vq):
    from app.qgen.models import CQuiz
    return CQuiz.query.filter_by(vquiz_id=vq.id).order_by(CQuiz.id).all()


def test_every_student_gets_the_same_order_or_the_same_quiz(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    vq, probs = quiz_of(teacher, 'P1', 'P2', 'P3', 'P4', 'P5', keep='')   # (shuffled)
    users = [ids('sam'), ids('kim')]
    # the same order: one order for everyone, each still his/her own numbers
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': users, 'same': 'order'})
    a, b = copies(vq)
    assert [cp.vproblem_id for cp in a.cproblems] == [cp.vproblem_id for cp in b.cproblems]
    # the exact same quiz: the very same problems, numbers and all
    for cq in copies(vq):
        db.session.delete(cq)
    db.session.commit()
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': users, 'same': 'all'})
    a, b = copies(vq)
    assert [(cp.vproblem_id, cp.conc_prob, cp.conc_ansr) for cp in a.cproblems] == \
           [(cp.vproblem_id, cp.conc_prob, cp.conc_ansr) for cp in b.cproblems]
    # (each has its own copy of the extra data, not one shared between them)
    assert a.cproblems[0].id != b.cproblems[0].id


def test_keep_the_quizs_order_for_one_assignment(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    vq, probs = quiz_of(teacher, 'K1', 'K2', 'K3', 'K4', 'K5', 'K6', keep='')   # (the quiz shuffles)
    for _ in range(3):
        teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')], 'keep_order': 'y', 'keep_order_set': '1'})
    for cq in copies(vq):
        assert [cp.vproblem_id for cp in cq.cproblems] == [p.id for p in probs]
    # without the box on the page (keep_order_set), the quiz's own setting: never forced to shuffle a kept order
    kept, kprobs = quiz_of(teacher, 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', keep='y')
    teacher.post('/quiz/assign', data={'vquiz': kept.id, 'users': [ids('sam')]})
    assert [cp.vproblem_id for cp in copies(kept)[0].cproblems] == [p.id for p in kprobs]


def test_how_many_times_repeats_a_problem(app_db):
    app, db = app_db
    from app.qgen.models import VQuiz
    teacher = login(app, 'teach')
    vq, probs = quiz_of(teacher, 'R1')
    teacher.post('/quiz/editvquiz/{}'.format(vq.id), data={'title': vq.title, 'vplist': json.dumps([probs[0].id] * 3), 'keep_order': 'y'})
    db.session.expire_all()
    assert json.loads(db.session.get(VQuiz, vq.id).vpid_lst) == [probs[0].id] * 3
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    assert len(copies(vq)[0].cproblems) == 3


def test_add_to_quizzes_page(app_db):
    app, db = app_db
    from app.qgen.models import VQuiz
    teacher = login(app, 'teach')
    q1, p1 = quiz_of(teacher, 'A1')
    q2, p2 = quiz_of(teacher, 'B1')
    extra, _ = quiz_of(teacher, 'C1')
    new = p1[0]
    # the page: the problems checked on Problems already checked, every quiz to pick from
    page = teacher.get('/quiz/addtoquiz/pick?problems={}'.format(p2[0].id)).data.decode()
    assert 'value="{}" id="ap-{}" checked'.format(p2[0].id, p2[0].id) in page and 'id="aq-{}"'.format(q1.id) in page
    # from the menu: nothing checked to begin with
    assert ' checked' not in teacher.get('/quiz/addtoquiz/pick').data.decode().split('id="add-problem-pick"')[1].split('id="add-quiz-pick"')[0].replace('data-stash-checked', '')
    # Add: at the end of each quiz checked, once
    teacher.post('/quiz/addtoquiz', data={'items': [p2[0].id], 'quiz': [q1.id, extra.id]})
    db.session.expire_all()
    assert json.loads(db.session.get(VQuiz, q1.id).vpid_lst) == [new.id, p2[0].id]
    assert p2[0].id in json.loads(db.session.get(VQuiz, extra.id).vpid_lst)
    # students are kept off it
    assert login(app, 'sam').get('/quiz/addtoquiz/pick').status_code in (302, 403)


def test_the_stashs_checked_scans_move_and_discard(app_db):
    app, db = app_db
    from app.qgen.models import ScanJob, ScanFolder
    teacher = login(app, 'teach')
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    a = ScanJob(author_id=ids('teach'), name='Book A', pages=1, data='{"pages": []}')
    b = ScanJob(author_id=ids('teach'), name='Book B', pages=1, data='{"pages": []}')
    f = ScanFolder(name='Week 2')
    db.session.add_all([a, b, f])
    db.session.commit()
    from app.qgen import scan as SC
    SC.put_away(a); SC.put_away(b)   # (stashed: the stash lists only those)
    db.session.commit()
    r = teacher.post('/quiz/scan/stash/move', data={'items': [a.id, b.id], 'to': f.id, 'stay': ''})
    assert r.status_code == 302
    db.session.expire_all()
    assert db.session.get(ScanJob, a.id).folder_id == f.id and db.session.get(ScanJob, b.id).folder_id == f.id
    # the Checked folder shows just the ones asked for
    page = teacher.get('/quiz/scan?stash=checked&checked={}'.format(a.id)).data.decode()
    assert 'value="{}" data-name="Book A"'.format(a.id) in page and 'data-name="Book B" aria-label' not in page
    teacher.post('/quiz/scan/stash/discard', data={'items': [a.id, b.id]})
    db.session.expire_all()
    assert db.session.get(ScanJob, a.id) is None and db.session.get(ScanJob, b.id) is None
    assert login(app, 'sam').post('/quiz/scan/stash/discard', data={'items': [1]}).status_code in (302, 403)
