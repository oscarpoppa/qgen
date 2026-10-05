import json
import random

import pytest

from app.qgen.qtypes import get_qtype, numbers_match

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
    assert errors == ['"6 / a" divides by zero for some values.']


def test_each_student_can_get_a_different_picture_with_matching_answer():
    qt = get_qtype('text')
    o = {'values': [], 'markup': 'friendly',
         'images': [{'file': 'cat.png', 'label': 'cat'}, {'file': 'dog.png', 'label': 'dog'}, {'file': 'owl.png', 'label': 'owl'}]}
    assert qt.validate('What animal is this?', '[picture]', o) == []
    seen = set()
    for seed in range(40):
        _, ansr, co = qt.instantiate('What animal is this?', '[picture]', o, random.Random(seed))
        assert co['image'] == ansr + '.png'
        seen.add(co['image'])
    assert len(seen) == 3


def test_picture_pool_without_labels_just_varies_the_image():
    qt = get_qtype('numeric')
    o = {'values': [{'name': 'a', 'kind': 'whole', 'min': 1, 'max': 3}], 'markup': 'friendly',
         'images': [{'file': 'x.png'}, {'file': 'y.png'}]}
    assert qt.validate('Count [a]', 'a', o) == []
    assert {qt.instantiate('Count [a]', 'a', o, random.Random(s))[2]['image'] for s in range(20)} == {'x.png', 'y.png'}


def test_picture_labels_must_all_be_filled_in():
    o = {'values': [], 'markup': 'friendly', 'images': [{'file': 'a.png', 'label': 'a'}, {'file': 'b.png'}]}
    assert 'Every picture needs a label' in ' '.join(get_qtype('text').validate('q', '[picture]', o))


def test_pick_several_pool_always_mixes_right_and_wrong():
    qt = get_qtype('choice_many')
    o = {'values': [], 'markup': 'friendly', 'choices': '*2\n*4\n*6\n*8\n3\n5\n7\n9', 'show_n': 4}
    for seed in range(200):
        _, _, co = qt.instantiate('Which are even?', '', o, random.Random(seed))
        assert len(co['choices']) == 4
        assert 1 <= len(co['correct']) <= 3


def test_country_capital_question():
    qt = get_qtype('text')
    o = {'markup': 'friendly', 'values': [{'name': 'country = capital', 'kind': 'list',
                                            'items': 'France = Paris, Japan = Tokyo, Peru = Lima'}]}
    assert qt.validate('What is the capital of [country]?', '[capital]', o) == []
    for seed in range(20):
        prob, ansr, _ = qt.instantiate('What is the capital of [country]?', '[capital]', o, random.Random(seed))
        assert {'France': 'Paris', 'Japan': 'Tokyo', 'Peru': 'Lima'}[prob.split('of ')[1].rstrip('?')] == ansr


def test_pick_several_other_correct_combinations():
    qt = get_qtype('choice_many')
    o = {'markup': 'friendly',
         'values': [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '4'},
                    {'name': 'b', 'kind': 'whole', 'min': '6', 'max': '8'}],
         'choices': '[a]\n[10 - a]\n[b]\n[10 - b]\n[a + 20]\n[b + 30]',
         'combos': '[a], [10 - a]\n[b], [10 - b]'}
    assert qt.validate('Check two numbers that add up to 10.', '', o) == []
    for seed in range(30):
        _, ansr, co = qt.instantiate('Check two numbers that add up to 10.', '', o, random.Random(seed))
        #two combinations, unless both came out as the same pair this time
        assert 1 <= len(co['combos']) <= 2 and (' or ' in ansr) == (len(co['combos']) == 2)
        for combo in co['combos']:
            assert sum(int(co['choices'][i]) for i in combo) == 10
            assert qt.grade(qt.to_stored([str(i) for i in combo]), ansr, co, o) == 1.0
        both = sorted(set(sum(co['combos'], [])) | {co['choices'].index(max(co['choices'], key=int))})
        assert qt.grade(qt.to_stored([str(i) for i in both]), ansr, co, o) == 0.0
        assert qt.grade(qt.to_stored([str(co['combos'][0][0])]), ansr, co, o) == 0.0


def test_combinations_with_a_pool_show_one_whole_combination():
    qt = get_qtype('choice_many')
    o = {'markup': 'friendly', 'values': [], 'show_n': 4,
         'choices': '3\n7\n4\n6\n1\n2\n5\n8', 'combos': '3, 7\n4, 6\n2, 8'}
    for seed in range(50):
        _, _, co = qt.instantiate('Check two numbers that add to 10', '', o, random.Random(seed))
        assert len(co['choices']) == 4 and co['combos']
        assert all(sum(int(co['choices'][i]) for i in c) == 10 for c in co['combos'])


def test_combination_typos_reported():
    o = {'markup': 'friendly', 'values': [], 'choices': '3\n7\n4\n6', 'combos': '3, 8'}
    errs = get_qtype('choice_many').validate('q', '', o)
    assert any('"8", which isn\'t one of the choices' in e for e in errs)


def test_combination_that_can_collapse_is_refused():
    o = {'markup': 'friendly', 'values': [{'name': 'b', 'kind': 'whole', 'min': '4', 'max': '6'}],
         'choices': '[b]\n[10 - b]\n1\n2', 'combos': '[b], [10 - b]'}
    errs = get_qtype('choice_many').validate('Check two that add to 10', '', o)
    assert any('same answer twice' in e for e in errs)


def test_fractions_are_understood():
    assert numbers_match('3/4', '0.75')
    assert numbers_match('1 1/2', '1.5')
    assert numbers_match('-2/3', '-0.6667')
    assert numbers_match('1/3, 1/2', '0.5, 0.3333')
    assert not numbers_match('3/4', '3, 4')


def test_precision_choices():
    from app.qgen.qtypes import numbers_match as m
    assert m('3.33', '3.3333', 'hundredths') and not m('3.3', '3.3333', 'hundredths')
    assert m('3', '3.4', 'whole') and not m('3.4', '3.4', 'whole') and not m('4', '3.4', 'whole')
    assert m('1/3', '0.3333', 'exact') and not m('0.33', '0.3333', 'exact')
    assert m('12.004', '12') and not m('12.02', '12')  # original rule unchanged
    qt = get_qtype('numeric')
    o = {'markup': 'friendly', 'values': [], 'precision': 'whole'}
    assert qt.grade('7', '6.5', {}, o) == 1.0 and qt.grade('6', '6.5', {}, o) == 0.0
    assert m('2.35', '2.345', 'hundredths') and not m('2.34', '2.345', 'hundredths')


@pytest.mark.parametrize('key', ['choice_one', 'choice_many'])
def test_full_pool_is_still_shuffled(key):
    qt = get_qtype(key)
    choices = '*A\nB\nC\nD\nE' if key == 'choice_one' else '*A\n*B\nC\nD\nE'
    o = {'markup': 'friendly', 'values': [], 'choices': choices, 'show_n': 5, 'shuffle': True}
    orders = {tuple(qt.instantiate('q', '', o, random.Random(s))[2]['choices']) for s in range(60)}
    assert len(orders) > 20                      # many different orders
    firsts = {qt.instantiate('q', '', o, random.Random(s))[2]['choices'][0] for s in range(60)}
    assert firsts == set('ABCDE')                # the right answer isn't stuck in one place


@pytest.mark.parametrize('key', ['choice_one', 'choice_many'])
def test_unshuffled_pool_keeps_teacher_order(key):
    qt = get_qtype(key)
    o = {'markup': 'friendly', 'values': [], 'choices': 'W1\nW2\n*R\nW3\nW4', 'show_n': 3, 'shuffle': False}
    for s in range(40):
        shown = qt.instantiate('q', '', o, random.Random(s))[2]['choices']
        assert shown == sorted(shown, key='W1 W2 R W3 W4'.split().index)
    positions = {qt.instantiate('q', '', o, random.Random(s))[2]['choices'].index('R') for s in range(40)}
    assert len(positions) > 1                    # R isn't always first


def test_unshuffled_combinations_keep_teacher_order():
    qt = get_qtype('choice_many')
    o = {'markup': 'friendly', 'values': [], 'show_n': 4, 'shuffle': False,
         'choices': '1\n3\n4\n6\n7\n9', 'combos': '1, 9\n3, 7\n4, 6'}
    for s in range(30):
        shown = qt.instantiate('q', '', o, random.Random(s))[2]['choices']
        assert shown == sorted(shown, key=int)
