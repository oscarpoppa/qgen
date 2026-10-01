import random

from app.qgen import friendly as F
from app.qgen.qtypes import get_qtype, read_complex, complex_match

Z = [{'name': 'z', 'kind': 'complex', 'min': '1', 'max': '5', 'im_min': '-4', 'im_max': '4'},
     {'name': 'w', 'kind': 'imaginary', 'min': '2', 'max': '6'}]


def env(**kw):
    e = F.start_env(True)
    e.update(kw)
    return e


def test_complex_math_and_display():
    e = env(a=3, b=4)
    shown = lambda f: F.format_num(F.evaluate(f, e))
    assert shown('a + b i') == '3 + 4i'
    assert shown('(a + b*i)^2') == '-7 + 24i'
    assert shown('conj(a + 2i)') == '3 - 2i'
    assert shown('abs(a + b*i)') == '5'
    assert shown('i^2') == '-1'
    assert shown('sqrt(-9)') == '3i'
    assert shown('-i') == '-i' and shown('1/(2i)') == '-0.5i'
    assert shown('re((1+2i)*(3-i))') == '5' and shown('im(2 - 7i)') == '-7'


def test_ordinary_problems_never_get_imaginary_numbers():
    num = get_qtype('numeric')
    plain = {'markup': 'friendly', 'values': [{'name': 'a', 'kind': 'whole', 'min': '-9', 'max': '9'}]}
    assert 'imaginary number' in num.validate('[a]', 'sqrt(a)', plain)[0] or "can't be worked out" in num.validate('[a]', 'sqrt(a)', plain)[0]
    assert 'imaginary number' in num.validate('[a]', 'a ^ 0.5', plain)[0]
    assert "isn't in your values table" in num.validate('[a]', 'a + 2i', plain)[0]
    # a value the teacher named i is just a number
    iv = {'markup': 'friendly', 'values': [{'name': 'i', 'kind': 'whole', 'min': '1', 'max': '5'}]}
    assert num.validate('[i] + 1', 'i + 1', iv) == []
    for seed in range(10):
        prob, ansr, _ = num.instantiate('[i] + 1', 'i + 1', iv, random.Random(seed))
        assert 'i' not in ansr and int(ansr) == int(prob.split(' ')[0]) + 1


def test_complex_values_and_problem():
    num = get_qtype('numeric')
    o = {'markup': 'friendly', 'values': Z}
    assert num.validate('What is ([z])([w])?', 'z * w', o) == []
    for seed in range(40):
        prob, ansr, co = num.instantiate('What is ([z])([w])?', 'z * w', o, random.Random(seed))
        assert co['complex']
        z = complex(read_complex(prob.split('(')[1].split(')')[0])[0])
        w = complex(read_complex(prob.split('(')[2].split(')')[0])[0])
        assert w.real == 0 and w.imag != 0 and z.imag != 0
        assert complex_match(F.format_num(z * w), ansr)
        assert num.grade(F.format_num(z * w).replace(' ', ''), ansr, co, o) == 1.0
        assert num.grade(F.format_num(z * w + 1), ansr, co, o) == 0.0


def test_reading_student_answers():
    assert read_complex('3+2i') == [3 + 2j]
    assert read_complex('3 - 2i, -i') == [3 - 2j, -1j]
    assert read_complex('2j') == [2j]
    assert read_complex('1/2 + 3/4i') == [0.5 + 0.75j]
    assert read_complex('hello') is None
    assert complex_match('3-2i, 3+2i', '3 + 2i, 3 - 2i')          # order doesn't matter
    assert complex_match('3.004 + 2i', '3 + 2i')                   # within 0.01
    assert not complex_match('3.004 + 2i', '3 + 2i', 'exact')
    assert not complex_match('3 + 2i', '3 + 2i, 3 - 2i')           # a root is missing
    assert not complex_match('2 + 3i', '3 + 2i')


def test_quadratic_with_complex_roots():
    num = get_qtype('numeric')
    o = {'markup': 'friendly', 'complex': True,
         'values': [{'name': 'p', 'kind': 'whole', 'min': '1', 'max': '4'},
                    {'name': 'q', 'kind': 'whole', 'min': '1', 'max': '4'}]}
    q = 'Solve x^2 - [2*p]x + [p^2 + q^2] = 0'
    a = '[p + q*i], [p - q*i]'
    assert num.validate(q, a, o) == []
    prob, ansr, co = num.instantiate(q, a, o, random.Random(3))
    assert num.grade(ansr.split(', ')[1] + ',' + ansr.split(', ')[0], ansr, co, o) == 1.0


def test_complex_cannot_be_ordered():
    tf = get_qtype('truefalse')
    o = {'markup': 'friendly', 'values': Z}
    assert 'compared' in tf.validate('[z] > [w]?', 'z > w', o)[0]
    assert tf.validate('Is |[z]| bigger than 1?', 'abs(z) > 1', o) == []
