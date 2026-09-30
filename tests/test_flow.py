"""End to end: a teacher builds and assigns a quiz, students take it, the
teacher grades the essay, and results, retakes and deletes all work."""
import io
import json
import os
import re

import pytest


@pytest.fixture
def app_db():
    from app import app, db
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        from app.user.models import User
        from app.qgen.models import VPGroup, VQGroup
        db.session.add_all([VPGroup(title='Archive'), VQGroup(title='Archive')])
        for name, admin in (('teach', True), ('sam', False), ('kim', False)):
            u = User(username=name, is_admin=admin)
            u.set_password('pw-for-tests')
            db.session.add(u)
        db.session.commit()
        yield app, db
        db.session.remove()
        db.drop_all()


def login(app, name):
    c = app.test_client()
    r = c.post('/login', data={'username': name, 'password': 'pw-for-tests'})
    assert r.status_code == 302
    return c


def png_bytes(color):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (40, 30), color).save(buf, 'PNG')
    buf.seek(0)
    return buf


def problem_form(qtype, title, question, answer='', values=(), images=(), **extra):
    data = {'qtype': qtype, 'title': title, 'question': question, 'answer': answer, 'shuffle': 'y'}
    for i, row in enumerate(values):
        for k, v in row.items():
            data['values-{}-{}'.format(i, k)] = v
    for i, img in enumerate(images):
        for k, v in img.items():
            data['images-{}-{}'.format(i, k)] = v
    data.update(extra)
    return data


AB = [{'name': 'a', 'kind': 'whole', 'min': '2', 'max': '40'},
      {'name': 'b', 'kind': 'whole', 'min': '2', 'max': '40', 'different_from': 'a'}]


def correct_answer(cp):
    """What a perfect student would submit for one concrete problem."""
    key = cp.vproblem.qtype
    if key in ('choice_one', 'truefalse'):
        return str(cp.conc_opts['correct'][0])
    if key == 'choice_many':
        return [str(i) for i in cp.conc_opts['correct']]
    if key == 'text':
        return cp.conc_ansr.splitlines()[0]
    if key == 'essay':
        return 'Because the <b>train</b> keeps going.'
    return cp.conc_ansr


def test_whole_school_week(app_db):
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz, CQuiz, CProblem
    teacher = login(app, 'teach')

    # --- pictures: drag-and-drop upload endpoint
    names = []
    for color in ('red', 'blue'):
        r = teacher.post('/upload/json', data={'file': (png_bytes(color), 'animal.png')},
                         content_type='multipart/form-data')
        body = r.get_json()
        assert body['ok'], body
        names.append(body['name'])
    assert names[0] != names[1], 'second upload must not overwrite the first'
    assert all(os.path.exists(os.path.join(app.config['STATIC_DIR'], n)) for n in names)
    listed = [i['name'] for i in teacher.get('/upload/imagelist').get_json()]
    assert set(names) <= set(listed)
    r = teacher.post('/upload/json', data={'file': (io.BytesIO(b'not an image'), 'x.png')},
                     content_type='multipart/form-data')
    assert not r.get_json()['ok']

    # --- one problem of every type
    forms = [
        problem_form('numeric', 'Add', '[a] + [b] = ?', 'a + b', AB),
        problem_form('text', 'Animal', 'What animal is in the picture?', '[picture]',
                     images=[{'file': names[0], 'label': 'cat'}, {'file': names[1], 'label': 'dog'}]),
        problem_form('choice_one', 'Times', '[a] × [b] = ?', '', AB, choices='*[a*b]\n[a*b+1]\n[a+b]'),
        problem_form('choice_many', 'Evens', 'Which are even? (select all)', '', [], choices='*2\n*4\n3\n5'),
        problem_form('truefalse', 'Bigger', 'True or false: [a] > [b]', 'a > b', AB),
        problem_form('essay', 'Why', 'Explain why the train keeps going.', '', [], grading_notes='Mentions inertia'),
    ]
    # the preview shows three examples and catches mistakes
    r = teacher.post('/quiz/previewvprob', data=forms[0])
    assert r.data.count(b'Example ') == 3
    bad = dict(forms[0], answer='a + bb')
    assert b'Did you mean' in teacher.post('/quiz/previewvprob', data=bad).data
    assert b'Did you mean' in teacher.post('/quiz/makevprob', data=bad).data
    for f in forms:
        r = teacher.post('/quiz/makevprob', data=f)
        assert r.status_code == 302, r.data.decode()[:500]
    probs = VProblem.query.order_by(VProblem.id).all()
    assert [p.qtype for p in probs] == ['numeric', 'text', 'choice_one', 'choice_many', 'truefalse', 'essay']

    # editing loads everything back and saves unchanged
    r = teacher.get('/quiz/editvprob/{}'.format(probs[0].id))
    assert b'value="a"' in r.data and b'value="40"' in r.data

    # --- the live helper
    hints = teacher.post('/quiz/checkvprob', data=dict(forms[0], question='[a] + [c] = ?')).get_json()['hints']
    assert any(h['action'] and h['action']['type'] == 'add_value' and h['action']['name'] == 'c' for h in hints)

    # --- quiz and assignment
    ids = ', '.join(str(p.id) for p in probs)
    r = teacher.post('/quiz/makevquiz', data={'title': 'Week 1', 'vplist': ids, 'shuffle_order': 'y'})
    assert r.status_code == 302
    vq = VQuiz.query.one()
    assert vq.shuffle_order
    qhints = teacher.post('/quiz/checkvquiz', data={'title': 'Week 1', 'vplist': ids}).get_json()['hints']
    assert any('written answer' in h['text'] for h in qhints)
    students = [u for u in __import__('app.user.models', fromlist=['User']).User.query.filter_by(is_admin=False)]
    r = teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [u.id for u in students]})
    assert r.status_code == 302
    sam_q, kim_q = [CQuiz.query.filter_by(assignee=u.id).one() for u in students]

    # anti-copying: the two students' versions differ
    def version(cq):
        return [(cp.vproblem_id, cp.conc_prob, tuple(cp.conc_opts.get('choices', ()))) for cp in cq.cproblems]
    assert version(sam_q) != version(kim_q)

    # --- a student can't open someone else's quiz
    sam = login(app, 'sam')
    r = sam.get('/quiz/take/{}'.format(kim_q.id))
    assert r.status_code == 302
    # and can't reach teacher pages
    assert sam.get('/quiz/makevprob').status_code == 302

    # --- sam takes the quiz, perfectly
    page = sam.get('/quiz/take/{}'.format(sam_q.id)).data.decode()
    assert page.count('class="qnum"') == 6
    for cp in sam_q.cproblems:
        assert cp.conc_prob.split(' ')[0].replace('<', '&lt;') in page  # question text shown as text
        if cp.conc_opts.get('image'):
            assert cp.conc_opts['image'] in page
    answers = {'Number{}'.format(cp.ordinal): correct_answer(cp) for cp in sam_q.cproblems}
    r = sam.post('/quiz/take/{}'.format(sam_q.id), data=answers)
    assert r.status_code == 302
    db.session.expire_all()
    sam_q = db.session.get(CQuiz, sam_q.id)
    assert sam_q.needs_review and not sam_q.completed
    assert b'Submitted' in sam.get('/quiz/take/{}'.format(sam_q.id)).data
    assert b'Mentions inertia' not in sam.get('/quiz/take/{}'.format(sam_q.id)).data

    # --- kim submits everything blank except the essay, also blank -> no review needed
    kim = login(app, 'kim')
    r = kim.post('/quiz/take/{}'.format(kim_q.id), data={})
    db.session.expire_all()
    kim_q = db.session.get(CQuiz, kim_q.id)
    assert kim_q.completed and kim_q.score == 0

    # --- the teacher grades sam's essay
    assert b'Week 1' in teacher.get('/quiz/review').data
    essay = [cp for cp in sam_q.cproblems if cp.vproblem.qtype == 'essay'][0]
    page = teacher.get('/quiz/review/{}'.format(sam_q.id)).data.decode()
    assert 'Mentions inertia' in page
    assert '&lt;b&gt;train&lt;/b&gt;' in page  # student's text escaped, never HTML
    item = {'items-0-cpid': essay.id, 'items-0-feedback': 'Good, but say why.',
            'items-0-highlights': json.dumps([[4, 13, 'right'], [0, 3, 'wrong']])}
    r = teacher.post('/quiz/review/{}'.format(sam_q.id), data=dict(item, save='Save draft'))
    assert r.status_code == 302
    r = teacher.post('/quiz/review/{}'.format(sam_q.id), data=dict(item, finalize='Finish'))
    assert r.status_code == 302  # finishing without a credit is refused...
    db.session.expire_all()
    assert not db.session.get(CQuiz, sam_q.id).completed
    r = teacher.post('/quiz/review/{}'.format(sam_q.id), data=dict(item, **{'items-0-credit': 60, 'finalize': 'Finish'}))
    db.session.expire_all()
    sam_q = db.session.get(CQuiz, sam_q.id)
    assert sam_q.completed and not sam_q.needs_review
    assert abs(sam_q.score - 100 * 5.6 / 6) < 0.01

    # --- sam's permanent transcript
    page = sam.get('/quiz/take/{}'.format(sam_q.id)).data.decode()
    assert '{:.0f}%'.format(sam_q.score) in page
    assert 'Good, but say why.' in page
    assert '<mark class="hl-right">' in page and '<mark class="hl-wrong">' in page
    assert '<b>train</b>' not in page
    assert 'Mentions inertia' not in page

    # --- home page and lists
    assert '★ 93%' in sam.get('/mypage').data.decode()
    for url in ('/quiz/listvp', '/quiz/listvq', '/quiz/listuser', '/userdet', '/images', '/nonimages',
                '/quiz/listcq/{}'.format(sam_q.id), '/quiz/editvquiz/{}'.format(vq.id), '/quiz/assign?vq={}'.format(vq.id)):
        assert teacher.get(url).status_code == 200, url

    # --- retake gives new values; delete removes the assignment and its answers
    r = teacher.post('/quiz/retcq/{}'.format(sam_q.id))
    assert CQuiz.query.filter_by(assignee=sam_q.assignee).count() == 2
    kim_problems, kim_id = [cp.id for cp in kim_q.cproblems], kim_q.id
    teacher.post('/quiz/delcq/{}'.format(kim_id))
    db.session.expire_all()
    assert db.session.get(CQuiz, kim_id) is None
    assert CProblem.query.filter(CProblem.id.in_(kim_problems)).count() == 0
    # a problem in use can't be deleted
    teacher.post('/quiz/delvp/{}'.format(probs[0].id))
    assert db.session.get(VProblem, probs[0].id) is not None


def test_pick_several_combinations_through_the_pages(app_db):
    app, db = app_db
    from app.qgen.models import VProblem
    teacher = login(app, 'teach')
    form = problem_form('choice_many', 'Make ten', 'Tick two numbers that add up to 10.', '',
                        [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '4'}],
                        choices='[a]\n[10 - a]\n5\n9', combos='[a], [10 - a]')
    assert teacher.post('/quiz/previewvprob', data=form).data.count(b'Example ') == 3
    assert teacher.post('/quiz/makevprob', data=form).status_code == 302
    vp = VProblem.query.one()
    assert vp.options['combos'] == '[a], [10 - a]'
    page = teacher.get('/quiz/editvprob/{}'.format(vp.id)).data.decode()
    assert '[a], [10 - a]' in page
    bad = dict(form, combos='[a], [10 - b]')
    assert b"isn&#39;t one of the choices" in teacher.post('/quiz/makevprob', data=bad).data


def test_question_groups_give_students_different_problems(app_db):
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.user.models import User
    teacher = login(app, 'teach')
    for n in range(5):
        f = problem_form('numeric', 'P{}'.format(n), '[a] + {} = ?'.format(n), 'a + {}'.format(n),
                         [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '50'}])
        assert teacher.post('/quiz/makevprob', data=f).status_code == 302
    p = [v.id for v in VProblem.query.order_by(VProblem.id)]
    lay = json.dumps([p[0], {'pick': 2, 'from': p[1:]}])
    bad = json.dumps([p[0], {'pick': 9, 'from': p[1:]}])
    assert b'not 9' in teacher.post('/quiz/makevquiz', data={'title': 'G', 'vplist': bad}).data
    assert teacher.post('/quiz/makevquiz', data={'title': 'Groups', 'vplist': lay, 'shuffle_order': 'y'}).status_code == 302
    vq = VQuiz.query.one()
    assert b'2 of these 4' in teacher.get('/quiz/listvq').data
    assert json.loads(teacher.get('/quiz/editvquiz/{}'.format(vq.id)).data.decode()
                      .split('id="vplist" name="vplist" type="hidden" value="')[1].split('"')[0].replace('&#34;', '"')) \
        == [p[0], {'pick': 2, 'from': p[1:]}]
    for i in range(8):
        u = User(username='s{}'.format(i)); u.set_password('pw-for-tests'); db.session.add(u)
    db.session.commit()
    ids = [u.id for u in User.query.filter(User.username.like('s%')).all()]
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': ids})
    sets = set()
    for uid in ids:
        got = [cp.vproblem_id for cp in CQuiz.query.filter_by(assignee=uid).one().cproblems]
        assert len(got) == 3 and p[0] in got and len(set(got)) == 3
        sets.add(frozenset(got))
    assert len(sets) > 1


def test_deleting_people_and_problems_keeps_records_consistent(app_db):
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz, CQuiz, CProblem, AICall
    from app.user.models import User
    teacher = login(app, 'teach')
    # a second teacher writes a problem and a quiz, grades, and uses the AI log
    t2 = User(username='t2', is_admin=True); t2.set_password('pw-for-tests'); db.session.add(t2); db.session.commit()
    other = login(app, 't2')
    f = problem_form('numeric', 'By t2', '[a] + 1', 'a + 1', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}])
    other.post('/quiz/makevprob', data=f)
    vp = VProblem.query.one()
    other.post('/quiz/makevquiz', data={'title': 'By t2', 'vplist': str(vp.id)})
    vq = VQuiz.query.one()
    sam = User.query.filter_by(username='sam').one()
    other.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam.id]})
    cq = CQuiz.query.one()
    cq.graded_by = t2.id
    db.session.add(AICall(user_id=t2.id, kind='values', request='x'))
    db.session.commit()
    cq_id, vp_id, vq_id, t2_id, sam_id = cq.id, vp.id, vq.id, t2.id, sam.id

    # deleting that teacher keeps their problem, quiz, grade and log, with the link cleared
    teacher.post('/deluser/{}'.format(t2_id))
    db.session.expire_all()
    assert db.session.get(User, t2_id) is None
    assert db.session.get(VProblem, vp_id).author_id is None
    assert db.session.get(VQuiz, vq_id).author_id is None
    assert db.session.get(CQuiz, cq_id).graded_by is None
    assert AICall.query.one().user_id is None

    # a problem with student answers can't be deleted, even once it's out of every quiz
    q = db.session.get(VQuiz, vq_id)
    q.vproblems = []
    db.session.commit()
    r = teacher.post('/quiz/delvp/{}'.format(vp_id), follow_redirects=True)
    assert b'student answer' in r.data and db.session.get(VProblem, vp_id) is not None

    # deleting a student removes their quizzes and answers
    teacher.post('/deluser/{}'.format(sam_id))
    db.session.expire_all()
    assert CQuiz.query.count() == 0 and CProblem.query.count() == 0
    # ...after which the problem can go
    teacher.post('/quiz/delvp/{}'.format(vp_id))
    db.session.expire_all()
    assert db.session.get(VProblem, vp_id) is None


def test_changes_need_a_real_form_from_this_site(app_db):
    """Delete/retake/release/reset can't be triggered by a link or by another website."""
    app, db = app_db
    from app.qgen.models import VProblem
    from app.user.models import User
    teacher = login(app, 'teach')
    f = problem_form('numeric', 'Keep me', '[a] + 1', 'a + 1', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}])
    teacher.post('/quiz/makevprob', data=f)
    vp_id = VProblem.query.one().id
    sam_id = User.query.filter_by(username='sam').one().id
    # a plain link (GET) does nothing
    assert teacher.get('/quiz/delvp/{}'.format(vp_id)).status_code == 405
    assert teacher.get('/deluser/{}'.format(sam_id)).status_code == 405
    # a form without this site's session token is refused
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        r = teacher.post('/quiz/delvp/{}'.format(vp_id), follow_redirects=True)
        assert b'out of date' in r.data
        teacher.post('/deluser/{}'.format(sam_id), data={'csrf_token': 'forged'})
        db.session.expire_all()
        assert db.session.get(VProblem, vp_id) is not None and db.session.get(User, sam_id) is not None
        # the real page's button works
        page = teacher.get('/quiz/listvp').data.decode()
        token = page.split('name="csrf_token" value="')[1].split('"')[0]
        teacher.post('/quiz/delvp/{}'.format(vp_id), data={'csrf_token': token})
        db.session.expire_all()
        assert db.session.get(VProblem, vp_id) is None
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_math_display_runs_in_safe_mode(app_db):
    app, db = app_db
    page = login(app, 'sam').get('/mypage').data.decode()
    assert "load: ['ui/safe']" in page and page.index('ui/safe') < page.index('MathJax-script')
