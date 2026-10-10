"""Answers with several numbers ("x, y", "(x, y)") and math that looks like math."""
from app.qgen import friendly as F
from app.qgen.friendly import tidy
from app.qgen.qtypes import get_qtype, numbers_match, complex_match
from test_flow import app_db, login, problem_form, take_page  # noqa: F401  (fixture)

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
    assert page.count('class="math-btn"') == 54  # three bars of 18: question, choices, exact form
    assert all('data-target="{}"'.format(t) in page for t in ('question', 'choices', 'answer_display'))
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


def test_math_helpers_are_for_numeric_problems_only(app_db):
    # they sit in a "t-numeric" box, which the page shows only for Numeric problems
    app, db = app_db
    page = login(app, 'teach').get('/quiz/makevprob').data.decode()
    toolbar = page.index('class="math-toolbar"')
    preview = page.index('id="math-preview"')
    for spot in (toolbar, preview):
        opening = page.rfind('<div class="t-numeric">', 0, spot)
        assert opening != -1, spot
        # nothing closes the t-numeric box between its start and the helper
        between = page[opening:spot]
        assert between.count('<div') - between.count('</div>') >= 1


# ---------------------------------------------------------------- math in answers

def test_students_may_type_math_answers():
    from app.qgen.qtypes import student_numbers
    assert student_numbers('2√3') == '3.4641016151' and student_numbers('√(12)') == '3.4641016151'
    assert student_numbers('(1+√5)/2') == '1.6180339887' and student_numbers('π/2') == '1.5707963268'
    assert student_numbers('2π') == '6.2831853072' and student_numbers('3^2') == '9'
    assert student_numbers('(√2, √3)') == '1.4142135624, 1.7320508076'
    # plain numbers are read as before (fractions, mixed numbers, lists)
    for plain in ('3/4', '1 1/2', '-2.5', '3, 5', ''):
        assert student_numbers(plain) is None
    # math that can't be worked out is never right (√-4 isn't read as -4)
    assert student_numbers('√-4') == '' and student_numbers('√(x)') == '' and student_numbers('9^9^9') == ''
    qt = get_qtype('numeric')
    assert qt.grade('2√3', '3.4641', {}, {}) == 1.0 and qt.grade('√-4', '-4', {}, {}) == 0.0
    assert qt.grade('3.46', '3.4641', {}, {}) == 1.0 and qt.grade('3/4', '0.75', {}, {}) == 1.0
    # a times sign from the math keys (×), or typed as x, ·, ÷ between numbers
    for typed in ('6×2', '6 × 2', '6x2', '6 X 2', '4·3', '24÷2', '3×(2+2)'):
        assert qt.grade(typed, '12', {}, {}) == 1.0, typed
    assert qt.grade('6×3', '12', {}, {}) == 0.0
    # drawn as real math (a full root sign), built from the formula, not the typed text
    assert qt.show_submitted('2√3', {}) == r'\( 2 \sqrt{3} \)  (= 3.4641)' and qt.show_submitted('3/4', {}) == '3/4'
    from app.qgen.qtypes import student_math
    assert student_math('(1+√5)/2') == r'\( \frac{1 + \sqrt{5}}{2} \)' and student_math('π/2') == r'\( \frac{\pi}{2} \)'
    assert student_math('(√2, √3)') == r'\( \left(\sqrt{2}, \sqrt{3}\right) \)'
    # nothing but numbers and math gets through
    assert student_math(r'√4 \href{x}{y}') is None and student_math('2√3 <b>') is None
    assert qt.show_submitted('√-4', {}) == "√-4 (couldn't be worked out)"


def test_exact_form_of_a_numeric_answer(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    N = [{'name': 'n', 'kind': 'whole', 'min': '2', 'max': '7'}]
    qt = get_qtype('numeric')
    assert qt.validate('Root of [n]?', 'sqrt(n)', {'values': N, 'answer_display': r'\( \sqrt{[n]} \)'}) == []
    errors = qt.validate('Root?', 'sqrt(n)', {'values': N, 'answer_display': r'\( \sqrt{[m]} \)'})
    assert any('"m"' in e for e in errors)  # checked like the question
    teacher = login(app, 'teach')
    r = teacher.post('/quiz/makevprob', data=problem_form('numeric', 'Root', r'What is \( \sqrt{[n]} \)?', 'sqrt(n)', N,
                                                          answer_display=r'\( \sqrt{[n]} \)'))
    assert r.status_code == 302
    vp = VProblem.query.one()
    assert vp.options['answer_display'] == r'\( \sqrt{[n]} \)'
    assert r'value="\( \sqrt{[n]} \)"' in teacher.get('/quiz/editvprob/{}'.format(vp.id)).data.decode()
    sam_id = User.query.filter_by(username='sam').one().id
    teacher.post('/quiz/makevquiz', data={'title': 'Roots', 'vplist': str(vp.id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    cp = cq.cproblems[0]
    n = int(cp.conc_prob.split('{')[1].split('}')[0])
    assert cp.conc_opts['display'] == r'\( \sqrt{%d} \)' % n
    # the student types math with the keypad's symbols; it's worked out and graded
    page = take_page(login(app, 'sam'), cq.id).data.decode()
    assert 'class="keypad"' in page and 'data-ins="√"' in page and 'data-ins="×"' in page
    with app.test_request_context():
        S.submit(cq, {1: '√{}'.format(n)})
    assert cq.score == 100
    results = login(app, 'sam').get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert r'\( \sqrt{%d} \)  (≈ ' % n in results and r'\( \sqrt{%d} \)  (= ' % n in results


def test_results_list_the_choices(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('choice_one', 'Pick', 'Which is 4?', '', [], choices='*4\n5\n6'))
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    ids = [p.id for p in VProblem.query.order_by(VProblem.id)]
    teacher.post('/quiz/makevquiz', data={'title': 'Mixed', 'vplist': '{}, {}'.format(*ids)})
    sam_id = User.query.filter_by(username='sam').one().id
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    pick = next(cp for cp in cq.cproblems if cp.conc_opts.get('choices'))
    wrong = next(i for i, c in enumerate(pick.conc_opts['choices']) if c != '4')
    with app.test_request_context():
        S.submit(cq, {pick.ordinal: str(wrong)})
    page = login(app, 'sam').get('/quiz/take/{}'.format(cq.id)).data.decode()
    # all three choices listed; the student's pick and the correct one marked
    assert page.count('class="choice-text"') == 3
    assert 'is-picked' in page and '>your answer</span>' in page and '✓ correct' in page
    # keypads only for numbers, and not on results
    assert 'class="keypad"' not in page


def test_formulas_know_pi():
    assert abs(F.evaluate('pi * r^2', {'r': 2}) - 12.566370614359172) < 1e-12
    assert F.evaluate('2 * π', {}) == F.evaluate('2 * pi', {})
    assert F.names_in(F.parse_expr('pi * r^2')) == {'r'}  # pi isn't a value to define
    assert F.evaluate('pi', {'pi': 3}) == 3  # a value of their own called pi wins
    R = [{'name': 'r', 'kind': 'whole', 'min': '1', 'max': '9'}]
    assert get_qtype('numeric').validate('Area of a circle with radius [r] feet?', 'pi * r^2', {'values': R}) == []
    assert get_qtype('numeric').validate('Area of a circle with radius [r] feet?', 'pi * [r]^2', {'values': R}) == []


def test_the_answer_has_formula_buttons(app_db):
    """A Numeric answer has its own buttons, writing formulas (sqrt(), pi), not display math."""
    app, db = app_db
    page = login(app, 'teach').get('/quiz/makevprob').data.decode()
    bar = page.split('aria-label="Formula buttons" data-target="answer"')[1].split('</div>')[0]
    assert 'data-formula="sqrt(@¶)"' in bar and 'data-formula="pi¶"' in bar and 'data-formula="pm"' in bar
    assert '\\sqrt' not in bar
    assert page.index('aria-label="Formula buttons"') < page.index('aria-label="Answer"')


def test_formulas_with_bracketed_values_are_worked_out():
    """sqrt([a]) means the square root of the value a: saved, graded and shown as numbers,
    never as the text "sqrt(3)" (which grading read as the number 3)."""
    env = {'a': 3, 'b': 4, 'r': 2, 'who': 'Maria'}
    assert F.fill_answer('sqrt([a]), -sqrt([a])', env) == '1.7321, -1.7321'
    assert F.fill_answer('pi * [r]^2', env) == '12.5664'
    assert F.fill_answer('[a] + 1', env) == '4'
    assert F.fill_answer('([a], [b])', env) == '(3, 4)'
    assert F.fill_answer('[a] mph', env) == '3 mph' and F.fill_answer('[who]', env) == 'Maria'  # not math: as before
    qt = get_qtype('numeric')
    # answers already saved the old way are worked out when graded and shown
    assert qt.grade('1.732, -1.732', 'sqrt(3), -sqrt(3)', {}, {}) == 1.0
    assert qt.grade('3, 3', 'sqrt(3), -sqrt(3)', {}, {}) == 0.0
    assert qt.grade('4', '3 + 1', {}, {}) == 1.0
    assert qt.show_correct('sqrt(3), -sqrt(3)', {'display': r'\( \sqrt{3} \)'}) == r'\( \sqrt{3} \)  (≈ 1.7321, -1.7321)'
    assert qt.show_correct('sqrt(3)', {}) == '1.7321'
    for plain in ('1.7321, -1.7321', '-4', '2.5e-05', '1 1/2', 'Maria'):
        assert F.worked_answer(plain) == plain


def test_examples_and_details_show_numbers(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    A = [{'name': 'a', 'kind': 'whole', 'min': '2', 'max': '9'}]
    page = teacher.post('/quiz/previewvprob', data=problem_form('numeric', 'Roots', r'\( x^2 = [a] \)', 'sqrt([a]), -sqrt([a])', A)).data.decode()
    assert 'Correct answer' in page and 'sqrt' not in page.split('Three example versions')[1]


def test_each_row_of_math_buttons_sits_under_its_label(app_db):
    """Label, then its buttons, then the box they write into (not above the label, where
    they looked like part of the field before)."""
    app, db = app_db
    page = login(app, 'teach').get('/quiz/makevprob').data.decode()
    for target in ('question', 'choices', 'answer_display'):
        label = page.index('<label for="{}"'.format(target))
        bar = page.index('data-target="{}"'.format(target))
        box = page.index('name="{}"'.format(target), bar)
        assert label < bar < box, target
        assert '<label' not in page[label + 6:bar], target  # its own label, not another field's
    # the exact form has a worked example with a value, kept as written (inside <code>, which the math display skips)
    assert 'if the answer is <code>sqrt([a])</code>, write <code>\\( \\sqrt{[a]} \\)</code>' in page
    assert 'sees √3 (≈ 1.7321)' in page


def test_every_bar_of_math_keys_looks_the_same(app_db):
    """Both kinds of key bar sit under the same small "Math keys" heading, with the keys they
    share in the same order; every bar starts folded, out of the way until it's clicked."""
    import re
    app, db = app_db
    page = login(app, 'teach').get('/quiz/makevprob').data.decode()
    bars = re.findall(r'<details class="math-keys"( open)?>\s*<summary class="math-keys-head"[^>]*>Math keys</summary>'
                      r'\s*<div class="math-toolbar"[^>]*data-target="(\w+)"(.*?)</div>\s*</details>', page, re.S)
    found = {target: (bool(opened), re.findall(r'<button[^>]*>([^<]+)</button>', keys)) for opened, target, keys in bars}
    assert set(found) == {'question', 'choices', 'answer', 'answer_display'}
    assert not any(opened for opened, keys in found.values())
    shared = ['x²', 'xⁿ', '√', 'ⁿ√', 'a⁄b', '×', '÷', 'π', '|x|', '±']
    for target, (opened, keys) in found.items():
        assert keys[:len(shared)] == shared, target
