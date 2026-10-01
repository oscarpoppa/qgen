"""Answers with several numbers ("x, y", "(x, y)") and math that looks like math."""
from app.qgen import friendly as F
from app.qgen.probspec import tidy
from app.qgen.qtypes import get_qtype, numbers_match, complex_match
from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)

XY = [{'name': 'x', 'kind': 'whole', 'min': '1', 'max': '9'},
      {'name': 'y', 'kind': 'whole', 'min': '10', 'max': '19'}]


# ---------------------------------------------------------------- splitting and working out

def test_split_list():
    assert F.split_list('x, y') == (['x', 'y'], False)
    assert F.split_list(' (x, y) ') == (['x', 'y'], True)
    assert F.split_list('x+1,  -y , 3') == (['x+1', '-y', '3'], False)
    # commas inside a function call don't split
    assert F.split_list('min(a, b)') == (['min(a, b)'], False)
    assert F.split_list('min(a, b), max(a, b)') == (['min(a, b)', 'max(a, b)'], False)
    # one formula in parentheses is just a formula
    assert F.split_list('(a + b)') == (['(a + b)'], False)
    assert F.split_list('(a + b) * c') == (['(a + b) * c'], False)
    assert F.split_list('x, ') == (['x', ''], False)


def test_fill_answer_lists():
    env = {'x': 3, 'y': -5}
    assert F.fill_answer('x, y', env) == '3, -5'
    assert F.fill_answer('(x, y)', env) == '(3, -5)'
    assert F.fill_answer('x + y, x * y', env) == '-2, -15'
    assert F.fill_answer('min(x, y)', env) == '-5'
    assert F.fill_answer('x / 2', env) == F.format_num(1.5)
    assert F.fill_answer('[x], [y]', env) == '3, -5'  # the bracket form still works


# ---------------------------------------------------------------- the problem page's checks

def test_pair_answers_are_checked_part_by_part():
    qt, opts = get_qtype('numeric'), {'values': XY}
    assert qt.validate('Point ([x], [y])?', 'x, y', opts) == []
    assert qt.validate('Point?', '(x, y)', opts) == []
    assert qt.validate('Sum and product?', 'x + y, x * y', opts) == []
    assert qt.validate('Two numbers?', '3, 5', opts) == []
    errors = qt.validate('?', 'x, ', opts)
    assert errors == ['The answer has an empty spot between commas. For a pair, write it like: x, y']
    errors = qt.validate('?', 'x, z, z + 1', opts)
    assert len(errors) == 1 and '"z"' in errors[0]  # each mistake said once
    assert any('"q"' in e for e in qt.validate('?', 'q', opts))  # a single formula is still checked


# ---------------------------------------------------------------- grading

def test_order_only_matters_when_asked():
    assert numbers_match('5, 3', '3, 5') and numbers_match('(5, 3)', '(3, 5)')
    assert not numbers_match('5, 3', '3, 5', ordered=True)
    assert numbers_match('(3, 5)', '3, 5', ordered=True) and numbers_match('3,5', '(3, 5)', ordered=True)
    assert not numbers_match('3', '3, 5') and not numbers_match('3, 5, 7', '3, 5', ordered=True)
    assert numbers_match('1/2, -3', '0.5, -3', ordered=True)  # fractions understood
    assert complex_match('2-i, 1+i', '1+i, 2-i')
    assert not complex_match('2-i, 1+i', '1+i, 2-i', ordered=True)
    assert complex_match('1+i, 2-i', '1+i, 2-i', ordered=True)
    qt = get_qtype('numeric')
    assert qt.grade('5, 3', '3, 5', {}, {'values': XY}) == 1.0
    assert qt.grade('5, 3', '3, 5', {}, {'values': XY, 'ordered': True}) == 0.0


# ---------------------------------------------------------------- math

def test_tidy_inside_math():
    assert tidy(r'\[ 1x^2 + 3x \]') == r'\[ x^2 + 3x \]'
    assert tidy(r'\frac{1x}{2}') == r'\frac{x}{2}' and tidy(r'\sqrt{1y}') == r'\sqrt{y}'
    assert tidy(r'\( 2x^2 + -3x + 1 \)') == r'\( 2x^2 - 3x + 1 \)'
    # left alone: a number before a command, 10x, and [placeholders]
    assert tidy(r'\(1\times 10^3\)') == r'\(1\times 10^3\)'
    assert tidy('10x + 1') == '10x + 1' and tidy('[1, 5]') == '[1, 5]'
    assert tidy(r'\( \text{1kg} \)') == r'\( \text{1kg} \)' and tidy(r'\frac{1}{2}x') == r'\frac{1}{2}x'
    assert tidy(r'\[ 1x^{1y} \]') == r'\[ x^{y} \]'


def test_placeholders_fill_inside_math():
    env = {'a': 2, 'b': -3, 'c': 1, 'n': 3}
    assert F.fill_question(r'Solve \( [a]x^2 + [b]x + [c] = 0 \)', env) == r'Solve \( 2x^2 - 3x + 1 = 0 \)'
    assert F.fill_question(r'\( \sqrt[[n]]{x} \), \( \frac{[a]}{[n]} \), \( x^{[n]+1} \)', env) == \
        r'\( \sqrt[3]{x} \), \( \frac{2}{3} \), \( x^{3+1} \)'


# ---------------------------------------------------------------- through the pages and the API

def test_pair_problem_through_the_pages(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    teacher = login(app, 'teach')
    page = teacher.get('/quiz/makevprob').data.decode()
    assert 'class="math-toolbar"' in page and 'id="math-preview"' in page and 'name="ordered"' in page
    assert page.count('class="math-btn"') == 18
    r = teacher.post('/quiz/makevprob', data=problem_form('numeric', 'Point', r'Plot \( ([x], [y]) \)', '(x, y)', XY, ordered='y'))
    assert r.status_code == 302
    vp = VProblem.query.one()
    assert vp.options['ordered'] is True
    import re
    box = re.search(r'<input[^>]*name="ordered"[^>]*>', teacher.get('/quiz/editvprob/{}'.format(vp.id)).data.decode()).group(0)
    assert 'checked' in box  # the setting comes back when editing
    # a student answers the pair; order matters here
    sam_id = User.query.filter_by(username='sam').one().id
    teacher.post('/quiz/makevquiz', data={'title': 'Points', 'vplist': str(vp.id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    x, y = [int(n) for n in cq.cproblems[0].conc_ansr.strip('()').split(',')]
    assert cq.cproblems[0].conc_ansr == '({}, {})'.format(x, y)
    with app.test_request_context():
        S.submit(cq, {1: '{}, {}'.format(y, x)})  # backwards
    assert cq.score == 0
    with app.test_request_context():
        again = S.retake(cq)
        x2, y2 = [int(n) for n in again.cproblems[0].conc_ansr.strip('()').split(',')]
        S.submit(again, {1: '({}, {})'.format(x2, y2)})
    assert again.score == 100
    # the results page shows the pair as the correct answer
    assert '<dt>Correct answer</dt><dd>({}, {})</dd>'.format(x2, y2) in login(app, 'sam').get('/quiz/take/{}'.format(again.id)).data.decode()


def test_ordered_option_through_the_api(app_db):
    app, db = app_db
    from test_api import Api
    t = Api(app, 'teach')
    r = t.post('/problems', json={'type': 'numeric', 'title': 'P', 'question': 'Point?', 'answer': '(x, y)',
                                  'options': {'values': XY, 'ordered': 'yes'}})
    assert r.status_code == 201, r.get_json()
    assert t.get('/problems/{}'.format(r.get_json()['id'])).get_json()['options']['ordered'] is True
    r = t.post('/problems', json={'type': 'numeric', 'title': 'R', 'question': 'Roots?', 'answer': 'x, y',
                                  'options': {'values': XY}})
    assert t.get('/problems/{}'.format(r.get_json()['id'])).get_json()['options']['ordered'] is False


def test_api_reads_yes_and_no_text(app_db):
    # "false" as text must mean no (bool("false") is True in Python)
    app, db = app_db
    from test_api import Api
    from app.api.teacher import flag
    assert flag('false') is False and flag('No') is False and flag('0') is False and flag('') is False
    assert flag('true') is True and flag('YES') is True and flag(1) is True and flag(None) is False
    t = Api(app, 'teach')
    r = t.post('/problems', json={'type': 'numeric', 'title': 'P', 'question': 'Point?', 'answer': '(x, y)',
                                  'options': {'values': XY, 'ordered': 'false', 'shuffle': 'no'}, 'calculator_ok': 'false'})
    got = t.get('/problems/{}'.format(r.get_json()['id'])).get_json()
    assert got['options']['ordered'] is False and got['options']['shuffle'] is False and got['calculator_ok'] is False
