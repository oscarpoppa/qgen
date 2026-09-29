import json
import random

import pytest

from app.qgen.qtypes import get_qtype, numbers_match
from app.qgen.probspec import process_spec

VALUES = [{'name': 'a', 'kind': 'whole', 'min': 2, 'max': 9},
          {'name': 'b', 'kind': 'whole', 'min': 2, 'max': 9, 'different_from': ['a']},
          {'name': 'who', 'kind': 'list', 'items': 'Maria, Li'}]


def opts(**kw):
    return dict(kw, values=VALUES, markup='friendly')


def make(key, question, answer, **kw):
    qt = get_qtype(key)
    o = opts(**kw)
    assert qt.validate(question, answer, o) == []
    return qt, o, qt.instantiate(question, answer, o, random.Random(7))


def numbers(text):
    import re
    return [int(n) for n in re.findall(r'-?\d+', text)]


def test_answer_uses_same_values_as_question():
    for seed in range(50):
        qt = get_qtype('numeric')
        prob, ansr, _ = qt.instantiate('[who] has [a] bags of [b] apples.', 'a * b', opts(), random.Random(seed))
        a, b = numbers(prob)
        assert ansr == str(a * b)


def test_choices_use_same_values_as_question():
    for seed in range(50):
        qt = get_qtype('choice_one')
        prob, ansr, co = qt.instantiate('[a] + [b] = ?', '', opts(choices='*[a+b]\n[a*b]\n[a-b]'), random.Random(seed))
        a, b = numbers(prob)
        right = co['choices'][co['correct'][0]]
        assert int(right) == a + b and ansr == right


def test_true_false_answer_follows_values():
    for seed in range(30):
        qt = get_qtype('truefalse')
        prob, ansr, co = qt.instantiate('True or false: [a] > [b]', 'a > b', opts(), random.Random(seed))
        a, b = numbers(prob)
        assert ansr == ('True' if a > b else 'False')
        assert co['choices'][co['correct'][0]] == ansr


def test_numeric_grading():
    qt, o, (prob, ansr, co) = make('numeric', '[a] * [b] = ?', 'a*b')
    assert qt.grade(ansr, ansr, co, o) == 1.0
    assert qt.grade(str(int(ansr) + 1), ansr, co, o) == 0.0
    assert qt.grade('', ansr, co, o) == 0.0


def test_numbers_match_checks_every_number():
    assert numbers_match('3, 5', '3, 5') and numbers_match('5, 3', '3, 5')
    assert not numbers_match('3, 9', '3, 5')  # used to pass: only the first number was checked
    assert numbers_match('0', '0') and not numbers_match('0, 7', '0, 5')
    assert numbers_match('12.004', '12') and numbers_match('0.001', '0.00100')


def test_text_grading_ignores_case_spaces_and_period():
    qt, o, (_, ansr, co) = make('text', 'Capital of France?', 'Paris\nParis, France')
    assert qt.grade('  paris. ', ansr, co, o) == 1.0
    assert qt.grade('paris,   france', ansr, co, o) == 1.0
    assert qt.grade('Lyon', ansr, co, o) == 0.0
    o['case_sensitive'] = True
    assert qt.grade('paris', ansr, co, o) == 0.0


def test_pick_one_show_n_always_has_one_correct():
    qt = get_qtype('choice_one')
    o = opts(choices='*right\nw1\nw2\nw3\nw4', show_n=3)
    for seed in range(30):
        _, _, co = qt.instantiate('q', '', o, random.Random(seed))
        assert len(co['choices']) == 3 and len(co['correct']) == 1
        assert co['choices'][co['correct'][0]] == 'right'


def test_pick_one_grading_and_storage():
    qt, o, (_, ansr, co) = make('choice_one', 'q', '', choices='*right\nwrong\nother')
    right = str(co['correct'][0])
    assert qt.grade(qt.to_stored(right), ansr, co, o) == 1.0
    assert qt.grade(qt.to_stored(None), ansr, co, o) == 0.0
    assert qt.show_submitted(qt.to_stored(right), co) == 'right'


def test_pick_several_needs_exact_set():
    qt, o, (_, ansr, co) = make('choice_many', 'Which are even?', '', choices='*2\n*4\n3\n5')
    right = [str(i) for i in co['correct']]
    assert qt.grade(qt.to_stored(right), ansr, co, o) == 1.0
    assert qt.grade(qt.to_stored(right[:1]), ansr, co, o) == 0.0
    assert qt.grade(qt.to_stored(right + [str(i) for i in range(4) if str(i) not in right][:1]), ansr, co, o) == 0.0


def test_duplicate_choices_merged():
    qt = get_qtype('choice_one')
    o = {'values': [{'name': 'a', 'kind': 'whole', 'min': 2, 'max': 2}], 'choices': '*[a+2]\n[a*2]\n[a+3]', 'markup': 'friendly'}
    _, _, co = qt.instantiate('q', '', o, random.Random(1))
    assert sorted(co['choices']) == ['4', '5'] and co['choices'][co['correct'][0]] == '4'


def test_essay_needs_instructor():
    qt, o, (_, ansr, co) = make('essay', 'Explain why [who] is right.', '')
    assert qt.grade('anything', ansr, co, o) is None
    assert not qt.auto_graded


def test_validation_messages():
    assert get_qtype('numeric').validate('[a] + [hrs]', 'a', opts()) == [
        'The question uses "hrs", which isn\'t in your values table.']
    assert 'Mark the correct choice' in get_qtype('choice_one').validate('q', '', opts(choices='a\nb'))[0]
    assert get_qtype('text').validate('q', '', opts()) == ['Please give at least one accepted answer.']
    assert get_qtype('numeric').validate('', 'a', opts()) == ['Please write the question.']


def test_divide_by_zero_found_before_saving():
    o = {'values': [{'name': 'a', 'kind': 'whole', 'min': 0, 'max': 3}], 'markup': 'friendly'}
    errors = get_qtype('numeric').validate('6 / [a]', '6 / a', o)
    assert errors == ['A formula divided by zero.']


@pytest.mark.parametrize('seed', range(5))
def test_legacy_markup_unchanged(seed):
    q, a = '{{a:ri(1,4)}} + {{b:ri(1,4)}} = ?', '{{a+b}}'
    prob, ansr, co = get_qtype('numeric').instantiate(q, a, {'markup': 'legacy'})
    x, y = numbers(prob)
    assert int(ansr) == x + y and co == {}
