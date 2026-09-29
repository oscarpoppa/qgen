import random

import pytest

from app.qgen import friendly as F

VALUES = [
    {'name': 'speed', 'kind': 'whole', 'min': 40, 'max': 80, 'step': 5},
    {'name': 'hours', 'kind': 'whole', 'min': 2, 'max': 5},
    {'name': 'who', 'kind': 'list', 'items': 'Maria, Ahmed, Li', 'pick_n': 2},
    {'name': 'price', 'kind': 'decimal', 'min': 1, 'max': 3, 'places': 2},
    {'name': 'dist', 'kind': 'calc', 'formula': 'speed × hours'},
]


def draws(values, n=200):
    rng = random.Random(1)
    return [F.draw_values(values, rng) for _ in range(n)]


def test_each_kind_stays_in_range():
    for env in draws(VALUES):
        assert 40 <= env['speed'] <= 80 and env['speed'] % 5 == 0
        assert 2 <= env['hours'] <= 5
        assert env['who1'] != env['who2'] and env['who'] == env['who1']
        assert 1 <= env['price'] <= 3 and round(env['price'], 2) == env['price']
        assert env['dist'] == env['speed'] * env['hours']


def test_all_integers_3_to_5_then_one_of_those():
    seen = {env['n'] for env in draws([{'name': 'n', 'kind': 'whole', 'min': 3, 'max': 5}])}
    assert seen == {3, 4, 5}


def test_nonzero_and_different_from():
    values = [{'name': 'a', 'kind': 'whole', 'min': -2, 'max': 2, 'nonzero': True},
              {'name': 'b', 'kind': 'whole', 'min': -2, 'max': 2, 'different_from': ['a']}]
    for env in draws(values):
        assert env['a'] != 0 and env['a'] != env['b']


def test_zero_decimal_places_gives_whole_numbers():
    for env in draws([{'name': 'x', 'kind': 'decimal', 'min': 1, 'max': 9, 'places': 0}], 50):
        assert isinstance(env['x'], int)


def test_placeholders_filled_and_other_brackets_left_alone():
    env = {'a': 3, 'b': -4, 'who': 'Li'}
    text = F.fill_question('[who] solves [a]x + [b] on [0, 5]; [a^2] and [x]', env)
    assert text == 'Li solves 3x - 4 on [0, 5]; 9 and [x]'


def test_math_symbols_people_type():
    env = {'a': 6, 'b': 3}
    assert F.evaluate('a × b', env) == 18
    assert F.evaluate('a ÷ b', env) == 2
    assert F.evaluate('a ^ 2', env) == 36
    assert F.evaluate('round(sqrt(a), 2)', env) == 2.45


@pytest.mark.parametrize('bad', ["__import__('os')", '(1).real', 'a.b', 'lambda: 1', '[1][0]', 'open("x")'])
def test_evaluator_rejects_non_math(bad):
    with pytest.raises(F.FriendlyError):
        F.evaluate(bad, {'a': 1})


def test_huge_power_rejected():
    with pytest.raises(F.FriendlyError, match='too large'):
        F.evaluate('2 ^ 1000', {})


def test_plain_language_errors():
    errors = F.validate_values([
        {'name': 'c', 'kind': 'whole', 'min': 5, 'max': 1},
        {'name': 'e', 'kind': 'calc', 'formula': 'spead * 2'},
        {'name': 'speed', 'kind': 'whole', 'min': 1, 'max': 2},
        {'name': '2x', 'kind': 'whole', 'min': 1, 'max': 2},
        {'name': 'w', 'kind': 'list', 'items': 'a, b', 'pick_n': 3},
        {'name': 'f', 'kind': 'whole', 'min': 1, 'max': 3, 'different_from': ['zz']},
    ])
    text = '\n'.join(errors)
    assert '"from" (5) must not be bigger than "to" (1)' in text
    assert 'Did you mean "speed"?' in text
    assert "can't be a name" in text
    assert 'picks 3 from a list of only 2' in text
    assert 'different from "zz"' in text


def test_calculation_loop_reported():
    errors = F.validate_values([{'name': 'a', 'kind': 'calc', 'formula': 'b + 1'},
                                {'name': 'b', 'kind': 'calc', 'formula': 'a + 1'}])
    assert any('loop' in e for e in errors)


def test_unknown_name_in_text_suggests_fix():
    errors = F.check_text('question', '[hrs] and [0, 5]', ['hours', 'speed'])
    assert errors == ['The question uses "hrs", which isn\'t in your values table. Did you mean "hours"?']


def test_impossible_different_from_reported():
    values = [{'name': 'a', 'kind': 'whole', 'min': 1, 'max': 1},
              {'name': 'b', 'kind': 'whole', 'min': 1, 'max': 1, 'different_from': ['a']}]
    with pytest.raises(F.FriendlyError, match='all different'):
        F.draw_values(values)


def test_true_false_conditions():
    env = {'a': 5, 'b': 3}
    assert F.evaluate_condition('a > b', env) is True
    assert F.evaluate_condition('a = b', env) is False
    assert F.evaluate_condition('a ≥ 5 and b < 4', env) is True
    assert F.evaluate_condition('False', env) is False


def test_matched_pairs_stay_together():
    capitals = {'France': 'Paris', 'Japan': 'Tokyo', 'Kenya': 'Nairobi', 'Peru': 'Lima'}
    row = {'name': 'country = capital', 'kind': 'list',
           'items': ', '.join('{} = {}'.format(k, v) for k, v in capitals.items())}
    assert F.validate_values([row]) == []
    assert F.known_names([row]) == ['country', 'capital']
    seen = set()
    for env in draws([row]):
        assert capitals[env['country']] == env['capital']
        seen.add(env['country'])
    assert seen == set(capitals)


def test_matched_pairs_pick_several():
    row = {'name': 'word = number', 'kind': 'list', 'items': 'one = 1, two = 2, three = 3, four = 4', 'pick_n': 2}
    for env in draws([row], 50):
        assert env['word1'] != env['word2']
        assert {'one': 1, 'two': 2, 'three': 3, 'four': 4}[env['word2']] == env['number2']
        assert F.evaluate('number1 + number2', env) == env['number1'] + env['number2']


def test_matched_pairs_errors():
    errs = F.validate_values([{'name': 'country = capital', 'kind': 'list', 'items': 'France = Paris, Japan'}])
    assert any('should have 2 parts' in e for e in errs)
    errs = F.validate_values([{'name': 'country = 2nd', 'kind': 'list', 'items': 'a = b'}])
    assert any("can't be a name" in e for e in errs)


def test_every_value_is_checked_for_divide_by_zero():
    from app.qgen.qtypes import get_qtype
    # a is 0 only once in 101 values: random sampling could miss it, the full check can't
    o = {'markup': 'friendly', 'values': [{'name': 'a', 'kind': 'whole', 'min': '0', 'max': '100'}]}
    errs = get_qtype('numeric').validate('What is 100 / [a]?', '100 / a', o)
    assert errs and 'divides by zero' in errs[0]
    o['values'][0]['nonzero'] = True
    assert get_qtype('numeric').validate('What is 100 / [a]?', '100 / a', o) == []


def test_other_special_cases_caught():
    from app.qgen.qtypes import get_qtype
    num = get_qtype('numeric')
    v = lambda lo, hi: {'markup': 'friendly', 'values': [{'name': 'a', 'kind': 'whole', 'min': lo, 'max': hi}]}
    assert "can't be worked out" in num.validate('[a]', 'sqrt(a)', v('-3', '3'))[0]
    assert 'ordinary number' in num.validate('[a]', 'a ^ 0.5', v('-3', '3'))[0]
    assert 'too large' in num.validate('[a]', '10 ^ a', v('1', '200'))[0]
    assert num.validate('[a]', 'sqrt(a)', v('0', '9')) == []
    # a hidden zero inside a calculated value is found too
    o = {'markup': 'friendly', 'values': [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'},
                                          {'name': 'd', 'kind': 'calc', 'formula': 'a - 5'}]}
    assert 'divides by zero' in num.validate('12 / [d]', '12 / d', o)[0]


def test_large_ranges_still_sampled():
    from app.qgen.qtypes import get_qtype
    o = {'markup': 'friendly', 'values': [{'name': 'x', 'kind': 'decimal', 'min': '1', 'max': '9', 'places': '2'}]}
    assert get_qtype('numeric').validate('[x] / 2', 'x / 2', o) == []
