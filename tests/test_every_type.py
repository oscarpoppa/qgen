"""Every kind of question, made the way a teacher makes it, in one quiz, taken by a student and
graded: each step lands on the right page, and every page reads sensibly (no leftover
[placeholders], "None" or template code)."""
import re

from test_flow import app_db, login, take_page, png_bytes, problem_form  # noqa: F401  (fixture)

AB = [{'name': 'a', 'kind': 'whole', 'min': '2', 'max': '9'},
      {'name': 'b', 'kind': 'whole', 'min': '2', 'max': '9', 'different_from': 'a'}]


def sensible(page, where):
    """Nothing a person shouldn't see: template code, Python's None, an unfilled value."""
    text = re.sub(r'<(script|style)\b.*?</\1>', '', page, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    for bad in ('{{', '{%', 'None', 'Traceback', '[a]', '[b]', '[picture]', 'built-in method'):
        assert bad not in text, '{}: "{}" shows on the page'.format(where, bad)


def upload(teacher, color, name):
    body = teacher.post('/upload/json', data={'file': (png_bytes(color), name)}, content_type='multipart/form-data').get_json()
    assert body['ok'], body
    return body['name']


def test_every_question_type_end_to_end(app_db):
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.user.models import User
    teacher = login(app, 'teach')
    cat, dog, page_pic = upload(teacher, 'red', 'p1.png'), upload(teacher, 'blue', 'p2.png'), upload(teacher, 'white', 'dots.png')

    # --- one problem of every kind, from the problem editor
    forms = {
        'numeric': problem_form('numeric', 'Add', 'What is [a] + [b]?', 'a + b', AB),
        'pair': problem_form('numeric', 'Point', 'Give the point ([a], [b]).', '(a, b)', AB, ordered='y'),
        'text': problem_form('text', 'Animal', 'What animal is in the picture?', '[picture]',
                             images=[{'file': cat, 'label': 'cat'}, {'file': dog, 'label': 'dog'}]),
        'choice_one': problem_form('choice_one', 'Times', 'What is [a] × [b]?', '', AB, choices='*[a*b]\n[a*b+1]\n[a+b]'),
        'choice_many': problem_form('choice_many', 'Ten', 'Check two numbers that add to 10.', '', [],
                                    choices='2\n8\n3\n7\n5', combos='2, 8\n3, 7'),
        'truefalse': problem_form('truefalse', 'Bigger', 'True or false: [a] is bigger than [b].', 'a > b', AB),
        'essay': problem_form('essay', 'Why', 'Explain why a ball stops rolling.', '', [], grading_notes='Mentions friction'),
        'paper': problem_form('paper', 'Dots', 'Connect the dots from 1 to 20.', 'A star', images=[{'file': page_pic, 'label': ''}]),
    }
    ids = {}
    for key, f in forms.items():
        # the helper has nothing to stop it, and says what each one needs
        hints = teacher.post('/quiz/checkvprob', data=f).get_json()['hints']
        assert not [h for h in hints if h['level'] == 'error'], (key, hints)
        # three examples, as students will see them
        preview = teacher.post('/quiz/previewvprob', data=f).data.decode()
        sensible(preview, 'preview ' + key)
        r = teacher.post('/quiz/makevprob', data=f)
        assert r.status_code == 302, (key, r.data.decode()[:600])
        vp = VProblem.query.order_by(VProblem.id.desc()).first()
        ids[key] = vp.id
        # back to Problems, with the new one shown
        assert r.headers['Location'].endswith('/quiz/listvp?show={}'.format(vp.id)), (key, r.headers['Location'])
        view = teacher.get('/quiz/viewvprob/{}'.format(vp.id)).data.decode()
        assert view.count('class="card sample-item"') == 3, key
        sensible(view, 'view ' + key)
    assert teacher.get('/quiz/listvp').status_code == 200

    # --- a quiz with all of them, in this order, and a pick-one-of-two group
    order = [ids['numeric'], ids['pair'], ids['text'], ids['choice_one'], ids['choice_many'],
             {'pick': 1, 'from': [ids['truefalse'], ids['essay']]}, ids['paper']]
    import json
    r = teacher.post('/quiz/makevquiz', data={'title': 'Everything', 'vplist': json.dumps(order)})
    assert r.status_code == 302
    vq = VQuiz.query.one()
    assert 'Everything' in teacher.get(r.headers['Location']).data.decode()
    view = teacher.get('/quiz/viewvquiz/{}'.format(vq.id)).data.decode()
    assert view.count('class="card sample-item"') == 7
    sensible(view, 'quiz view')

    # --- assign: a paper page in it, so straight to printing one copy for the student
    ava = User(username='ava', is_admin=False)
    ava.set_password('pw-for-tests')
    db.session.add(ava)
    db.session.commit()
    r = teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ava.id]})
    assert '/quiz/print/{}'.format(vq.id) in r.headers['Location']
    printing = teacher.get(r.headers['Location']).data.decode()
    assert printing.count('class="paper-sheet"') == 1 and 'ava' in printing and page_pic in printing
    sensible(printing, 'print page')
    # it waits on Home and My quizzes (gold: new)
    student = login(app, 'ava')
    home = student.get('/home').data.decode()
    assert 'Everything' in home and 'class="quiz-is-new"' in home
    sensible(home, 'Home')
    mine = student.get('/mypage').data.decode()
    assert 'quiz-card quiz-is-new' in mine
    sensible(mine, 'My quizzes')

    # --- the start card, then the quiz: each kind gets its own way to answer
    cq = CQuiz.query.one()
    start = student.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'Start the quiz' in start
    page = take_page(student, cq.id).data.decode()
    sensible(page, 'take page')
    assert page.count('<section class="card question"') == 7  # five, one of the group of two, the paper page
    by = {cp.vproblem.qtype if cp.vproblem_id != ids['pair'] else 'pair': cp for cp in cq.cproblems}

    def field(cp):
        return re.search(r'<section class="card question" data-q="{}".*?</section>'.format(cp.ordinal), page, re.S).group(0)
    assert 'class="keypad"' in field(by['numeric']) and 'data-ins="×"' in field(by['numeric'])
    assert 'type="radio"' in field(by['choice_one']) and 'type="checkbox"' in field(by['choice_many'])
    assert 'Check every correct answer.' in field(by['choice_many'])
    assert 'Do this one on paper' in field(by['paper']) and 'data-paper' in field(by['paper'])
    pic = by['text'].conc_opts['image']
    assert pic in field(by['text']) and 'cat' not in field(by['text']).replace(pic, '') and 'dog' not in field(by['text']).replace(pic, '')
    group = by.get('truefalse') or by.get('essay')
    assert ('type="radio"' if 'truefalse' in by else '<textarea') in field(group)

    # --- answers: right for the automatic ones, close for the picture one, an essay if it came up
    answers = {
        by['numeric']: by['numeric'].conc_ansr,
        by['pair']: by['pair'].conc_ansr,
        by['text']: 'a small ' + by['text'].conc_ansr.splitlines()[0],  # "a small cat": the teacher checks it
        by['choice_one']: str(by['choice_one'].conc_opts['correct'][0]),
        by['choice_many']: [str(i) for i, c in enumerate(by['choice_many'].conc_opts['choices']) if c in ('2', '8')],
    }
    if 'truefalse' in by:
        answers[by['truefalse']] = str(by['truefalse'].conc_opts['correct'][0])
    else:
        answers[by['essay']] = 'Friction slows it down.'
    data = {'Number{}'.format(cp.ordinal): a for cp, a in answers.items()}
    r = student.post('/quiz/take/{}'.format(cq.id), data=data)
    assert r.status_code == 302 and r.headers['Location'].endswith('/quiz/take/{}'.format(cq.id))
    waiting = student.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'Handed in!' in waiting
    sensible(waiting, 'handed-in page')
    db.session.expire_all()
    cq = db.session.get(CQuiz, cq.id)
    assert cq.needs_review and not cq.completed
    credit = {cp.vproblem.qtype if cp.vproblem_id != ids['pair'] else 'pair': cp.credit for cp in cq.cproblems}
    assert credit['numeric'] == credit['pair'] == credit['choice_one'] == credit['choice_many'] == 1.0
    assert credit['text'] is None and credit['paper'] is None  # the teacher's to give
    assert credit.get('truefalse', 1.0) == 1.0

    # --- grading: it waits in Grading with the three for the teacher
    assert 'Everything' in teacher.get('/quiz/review').data.decode()
    review = teacher.get('/quiz/review/{}'.format(cq.id)).data.decode()
    sensible(review, 'grading page')
    assert 'check this answer' in review and 'Done on paper' in review and 'A star' in review
    rows = re.findall(r'name="items-(\d+)-cpid"[^>]*value="(\d+)"|value="(\d+)"[^>]*name="items-(\d+)-cpid"', review)
    cpids = {int(m[0] or m[3]): int(m[1] or m[2]) for m in rows}
    teacher_parts = [cp for cp in cq.cproblems if cp.credit is None]
    assert sorted(cpids.values()) == sorted(cp.id for cp in teacher_parts)
    grades = {}
    for k, cpid in cpids.items():
        grades['items-{}-cpid'.format(k)] = cpid
        grades['items-{}-credit'.format(k)] = 100
    r = teacher.post('/quiz/review/{}'.format(cq.id), data=dict(grades, finalize='Finish'))
    assert r.status_code == 302 and r.headers['Location'].endswith('/quiz/review')
    db.session.expire_all()
    cq = db.session.get(CQuiz, cq.id)
    assert cq.completed and cq.score == 100

    # --- the student's results: every question, sensibly
    done = student.get('/quiz/take/{}'.format(cq.id)).data.decode()
    sensible(done, 'results page')
    assert '100%' in done and 'Done on paper.' in done and done.count('class="card question"') == 7
    # and the teacher's results pages
    for url in ('/quiz/results/{}'.format(vq.id), '/quiz/listuser/{}'.format(ava.id), '/quiz/listcq/{}'.format(cq.id),
                '/quiz/results', '/quiz/listuser', '/dashboard'):
        r = teacher.get(url)
        assert r.status_code == 200, url
        sensible(r.data.decode(), url)


def test_problem_history(app_db):
    """A problem's History: every handed-in answer to it, by quiz, like a quiz's Results."""
    app, db = app_db
    from app.qgen.models import VProblem, CQuiz
    from app.user.models import User
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('text', 'Capital', 'What is the capital of France?', 'Paris'))
    vp = VProblem.query.one()
    page = teacher.get('/quiz/listvp').data.decode()
    assert 'href="/quiz/problem-results/{}"'.format(vp.id) not in page  # nobody has had it yet
    for title in ('Geo 1', 'Geo 2'):
        teacher.post('/quiz/makevquiz', data={'title': title, 'vplist': str(vp.id)})
    from app.qgen.models import VQuiz
    for vq in VQuiz.query.all():
        teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [u.id for u in User.query.filter_by(is_admin=False)]})
    answers = {'sam': 'Lyon', 'kim': 'Lyon'}
    for name in ('sam', 'kim'):
        s = login(app, name)
        for cq in CQuiz.query.filter_by(assignee=User.query.filter_by(username=name).one().id):
            take_page(s, cq.id)
            s.post('/quiz/take/{}'.format(cq.id), data={'Number1': answers[name] if cq.vquiz.title == 'Geo 1' else 'Paris'})
    page = teacher.get('/quiz/listvp').data.decode()
    assert 'href="/quiz/problem-results/{}"'.format(vp.id) in page
    page = teacher.get('/quiz/problem-results/{}'.format(vp.id)).data.decode()
    sensible(page, 'problem history')
    assert '<h1>Problem history: Capital</h1>' in page and '>History</a>' in teacher.get('/quiz/listvp').data.decode()
    assert 'data-level="open" data-level-of="#problem-results"' in page  # Expand all / Collapse all over its quizzes
    assert '<h1>Quiz results: Geo 1</h1>' in teacher.get('/quiz/results/{}'.format(VQuiz.query.filter_by(title='Geo 1').one().id)).data.decode()
    home = login(app, 'sam').get('/home').data.decode()
    assert 'data-level-of="#home-boxes"' in home and 'id="home-boxes"' in home
    assert '4 answers from 2 students' in page and 'average 50%' in page and '2 fully right' in page
    assert 'Geo 1' in page and 'Geo 2' in page and page.count('data-name="') == 4
    assert 'Most common wrong answers' in page and '<strong>Lyon</strong> <span class="muted">(2 times)</span>' in page
    assert teacher.get('/quiz/problem-results/999').status_code == 302  # gone: back to Problems
    assert login(app, 'sam').get('/quiz/problem-results/{}'.format(vp.id)).status_code == 302  # teachers only
