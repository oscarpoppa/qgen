"""Teacher-friendly problem markup.

A problem has a list of random values, each described by a small dict
(a "row" on the problem page), and text containing [name] or [formula]
placeholders.  For example:

    values:   speed  Whole number  from 40 to 80
              hours  Whole number  from 2 to 5
    question: A train goes [speed] mph for [hours] hours. How far does it go?
    answer:   speed * hours

Everything here is plain data in, plain data out: no eval(), and every
problem is checked with validate() before it is saved.
"""
import ast
import cmath
import itertools
import math
import operator
import random
import re
from difflib import get_close_matches

def tidy(prob):
    """Aesthetics for a filled-in question: '+ -3' becomes '- 3', '+ 0x' goes, '1x' becomes 'x'."""
    #turn '...+/- -...' into '...-/+ ...'
    prob = re.sub(r'\+\s*\-', '- ', prob)
    prob = re.sub(r'\-\s*\-', '+ ', prob)
    #turn '+ 0x' into ''
    prob = re.sub(r'[\+\-]\s*0[a-zA-Z]+', '', prob)
    #turn '+ 1x' into '+ x'
    prob = re.sub(r'([\+\-\(\=\,]\s*)1([a-zA-Z]+)', '\\1\\2', prob)
    #...and right after a math opener \[ or inside braces, {1x} -> {x}: one-letter
    #variables only, so units like \text{1kg} stay as typed
    prob = re.sub(r'(\\\[\s*|\{\s*)1([a-zA-Z])(?![a-zA-Z])', '\\1\\2', prob)
    return prob


KINDS = {
    'whole': 'Whole number',
    'decimal': 'Decimal',
    'list': 'Pick from list',
    'calc': 'Calculated',
    'imaginary': 'Imaginary number (bi)',
    'complex': 'Complex number (a + bi)',
}
#choosing one of these kinds turns complex numbers on for the problem
COMPLEX_KINDS = ('imaginary', 'complex')

FUNCS = {
    'sqrt': math.sqrt,
    'abs': abs,
    'round': round,
    'min': min,
    'max': max,
    #for complex numbers: real part, imaginary part, conjugate
    're': lambda z: z.real,
    'im': lambda z: z.imag if isinstance(z, complex) else 0,
    'conj': lambda z: z.conjugate(),
}

#names a formula may use without defining them (a value with the same name wins)
CONSTANTS = {'pi': math.pi}

#an env holding this key allows complex numbers, with i = sqrt(-1); only
#problems with "Use complex numbers" checked ever get it
COMPLEX = '__complex__'

MAX_TRIES = 100
NAME_PATT = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
PLACEHOLDER_PATT = re.compile(r'\[([^\[\]]+)\]')


class FriendlyError(ValueError):
    """A problem with the teacher's input, worded for the teacher."""


# ---------------------------------------------------------------- math

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def normalize_expr(expr):
    """Accept the symbols people actually type: ^ for powers, x-like signs,
    and 2i for 2 times i."""
    expr = (expr.replace('^', '**').replace('×', '*').replace('÷', '/')
                .replace('−', '-').replace('·', '*').replace('√', 'sqrt').replace('π', 'pi').strip())
    #2i, (a+b)i, and "b i" (a name, a space, then i) all mean times i
    expr = re.sub(r'(\d|\))\s*i\b', r'\1*i', expr)
    return re.sub(r'\b([A-Za-z_]\w*)\s+i\b', r'\1*i', expr)


def parse_expr(expr):
    """Parse a formula; raise FriendlyError if it isn't plain math."""
    try:
        tree = ast.parse(normalize_expr(expr), mode='eval')
    except SyntaxError:
        raise FriendlyError('"{}" isn\'t a formula I can read.'.format(expr))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Load)
                      + tuple(_BINOPS) + tuple(_UNARY)):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            continue
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in FUNCS and not node.keywords:
            continue
        raise FriendlyError('"{}" can only use numbers, value names, + - * / ^ and '
                            'sqrt, abs, round, min, max, pi (and re, im, conj for complex numbers).'.format(expr))
    return tree


def names_in(tree):
    """Value names used by a parsed formula (function names excluded)."""
    funcs = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - funcs - set(CONSTANTS)


def _eval(node, env):
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in env and node.id in CONSTANTS:
            return CONSTANTS[node.id]
        return env[node.id]
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_eval(node.operand, env))
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, env), _eval(node.right, env)
        if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e6):
            raise FriendlyError('That power is too large to work out.')
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.Call):
        args = [_eval(a, env) for a in node.args]
        if node.func.id == 'sqrt' and env.get(COMPLEX):
            return cmath.sqrt(*args)
        return FUNCS[node.func.id](*args)
    raise FriendlyError('Unsupported formula.')


def evaluate(expr, env):
    """Evaluate a formula against the drawn values.

    A formula that is just one name returns that value as-is, so words
    from a pick-list work in placeholders.
    """
    tree = expr if isinstance(expr, ast.Expression) else parse_expr(expr)
    if isinstance(tree.body, ast.Name) and tree.body.id in env:
        return env[tree.body.id]
    for name in names_in(tree):
        if isinstance(env[name], bool) or not isinstance(env[name], (int, float, complex)):
            raise FriendlyError('"{}" is a word, so it can\'t be used in math.'.format(name))
    try:
        result = _eval(tree, env)
    except FriendlyError:
        raise
    except ZeroDivisionError:
        raise FriendlyError('"{}" divides by zero for some values.'.format(_show(expr)))
    except (ValueError, OverflowError, TypeError):
        raise FriendlyError('"{}" can\'t be worked out for some values (for example, the square root of a negative number).'.format(_show(expr)))
    if isinstance(result, complex):
        if abs(result.imag) < 1e-12:
            result = result.real
        elif not env.get(COMPLEX):
            #never let an imaginary number into an ordinary problem
            raise FriendlyError('"{}" gives an imaginary number for some values. If that\'s intended, '
                                'check "Use complex numbers"; otherwise change the formula or ranges.'.format(_show(expr)))
        elif not (math.isfinite(result.real) and math.isfinite(result.imag)):
            raise FriendlyError('"{}" doesn\'t give an ordinary number for some values.'.format(_show(expr)))
    if isinstance(result, float) and not math.isfinite(result):
        raise FriendlyError('"{}" doesn\'t give an ordinary number for some values.'.format(_show(expr)))
    return result


def _show(expr):
    return ast.unparse(expr).replace('**', '^') if isinstance(expr, ast.AST) else str(expr)


_COMPARE = {
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
}
TRUE_WORDS = {'true', 'yes', 't', 'y'}
FALSE_WORDS = {'false', 'no', 'f', 'n'}


def parse_condition(expr):
    """Parse 'a > b', 'a = b and b < 10', or plain True/False for true/false
    questions.  Returns (kind, payload)."""
    word = (expr or '').strip().lower()
    if word in TRUE_WORDS or word in FALSE_WORDS:
        return 'const', word in TRUE_WORDS
    text = normalize_expr(expr or '')
    #people write = for "equals"
    text = re.sub(r'(?<![<>!=])=(?!=)', '==', text).replace('≠', '!=').replace('≤', '<=').replace('≥', '>=')
    try:
        tree = ast.parse(text, mode='eval')
    except SyntaxError:
        raise FriendlyError('The answer should be True, False, or a comparison like "a > b".')
    parts = []
    def split(node):
        if isinstance(node, ast.BoolOp):
            for v in node.values:
                split(v)
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _COMPARE:
            parts.append((ast.Expression(body=node.left), type(node.ops[0]), ast.Expression(body=node.comparators[0])))
        else:
            raise FriendlyError('The answer should be True, False, or a comparison like "a > b".')
    split(tree.body)
    if isinstance(tree.body, ast.BoolOp) and not isinstance(tree.body.op, ast.And):
        raise FriendlyError('Only "and" can join comparisons in a true/false answer.')
    #each side must itself be plain math
    for left, _, right in parts:
        parse_expr(ast.unparse(left.body))
        parse_expr(ast.unparse(right.body))
    return 'compare', parts


def condition_names(expr):
    kind, payload = parse_condition(expr)
    if kind == 'const':
        return set()
    names = set()
    for left, _, right in payload:
        names |= names_in(left) | names_in(right)
    return names


def evaluate_condition(expr, env):
    kind, payload = parse_condition(expr)
    if kind == 'const':
        return payload
    try:
        return all(_COMPARE[op](evaluate(left, env), evaluate(right, env)) for left, op, right in payload)
    except TypeError:
        raise FriendlyError('Complex numbers can only be compared with = or ≠ (use abs(z) to compare sizes).')


def _tidy(x):
    """Round away floating-point dust (so 2.9999999999 is 3) before showing a part."""
    r = round(x, 9)
    return 0.0 if r == 0 else (int(r) if r == int(r) else r)


def format_num(val):
    """Show numbers the way a person would write them; complex as 3 + 2i."""
    if isinstance(val, complex):
        re_part, im_part = _tidy(val.real), _tidy(val.imag)
        if im_part == 0:
            return format_num(re_part)
        coef = {1: '', -1: '-'}.get(im_part, format_num(im_part))
        imag = coef + 'i'
        if re_part == 0:
            return imag
        return '{} {} {}'.format(format_num(re_part), '-' if im_part < 0 else '+', imag.lstrip('-'))
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, float):
        if abs(val - round(val)) < 1e-9:
            return str(int(round(val)))
        return '{:.4f}'.format(val).rstrip('0').rstrip('.')
    return str(val)


# ---------------------------------------------------------------- values

def _num(row, key, label, integer=False):
    raw = row.get(key)
    if raw is None or str(raw).strip() == '':
        raise FriendlyError('Please fill in "{}" for {}.'.format(label, row.get('name') or 'this value'))
    try:
        val = float(raw)
    except (TypeError, ValueError):
        raise FriendlyError('"{}" for {} must be a number.'.format(label, row.get('name')))
    if integer:
        if val != int(val):
            raise FriendlyError('"{}" for {} must be a whole number.'.format(label, row.get('name')))
        return int(val)
    return val


def row_names(row):
    """Names a row defines. A pick-from-list row may define matched columns:
    name "country = capital" with items "France = Paris, Japan = Tokyo"."""
    name = (row.get('name') or '').strip()
    if row.get('kind') == 'list' and '=' in name:
        return [n.strip() for n in name.split('=')]
    return [name]


def _value(text):
    text = str(text).strip()
    try:
        num = float(text)
        return int(num) if num == int(num) and '.' not in text else num
    except ValueError:
        return text


def _items(row):
    """List items as tuples, one entry per name in row_names(row)."""
    items = row.get('items') or []
    if isinstance(items, str):
        items = items.split(',')
    width = len(row_names(row))
    out = []
    for item in items:
        item = str(item).strip()
        if not item:
            continue
        parts = [p.strip() for p in item.split('=')] if width > 1 else [item]
        if len(parts) != width:
            raise FriendlyError('In the list for {}, "{}" should have {} parts separated by "=" (like "France = Paris").'
                                .format(row.get('name'), item, width))
        out.append(tuple(_value(p) for p in parts))
    return out


def _whole_range(row):
    """range() of allowed whole numbers (zero may still need skipping)."""
    lo, hi = _num(row, 'min', 'from', True), _num(row, 'max', 'to', True)
    step = _num(row, 'step', 'in steps of', True) if str(row.get('step') or '').strip() else 1
    if lo > hi:
        raise FriendlyError('For {}, "from" ({}) must not be bigger than "to" ({}).'.format(row['name'], lo, hi))
    if step < 1:
        raise FriendlyError('For {}, "in steps of" must be 1 or more.'.format(row['name']))
    rng = range(lo, hi + 1, step)
    if row.get('nonzero') and list(rng[:2]) == [0] and len(rng) == 1:
        raise FriendlyError('For {}, there are no numbers to choose from.'.format(row['name']))
    return rng


def _imag_row(row):
    """The imaginary-part range of a complex value, as a row _whole_range understands."""
    return {'name': '{} (imaginary part)'.format(row.get('name')), 'min': row.get('im_min'), 'max': row.get('im_max')}


def uses_complex(values):
    return any(r.get('kind') in COMPLEX_KINDS for r in values)


def _places(row):
    places = row.get('places')
    if places in (None, ''):
        return 1
    try:
        return int(places)
    except (TypeError, ValueError):
        raise FriendlyError('Decimal places for {} must be a whole number.'.format(row.get('name')))


def _pick_n(row):
    raw = row.get('pick_n')
    if raw in (None, ''):
        return 1
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise FriendlyError('"How many to pick" for {} must be a whole number.'.format(row.get('name')))


def pick_names(row):
    """Names a row makes available: 'who' plus who1..whoN for pick-N lists
    (for matched columns, each column's name gets the same treatment)."""
    n = _pick_n(row) if row.get('kind') == 'list' else 1
    names = []
    for name in row_names(row):
        names += [name] + (['{}{}'.format(name, i) for i in range(1, n + 1)] if n > 1 else [])
    return names


def _draw(row, env, rng):
    kind = row.get('kind')
    if kind == 'whole':
        choices = _whole_range(row)
        val = rng.choice(choices)
        while row.get('nonzero') and val == 0:
            val = rng.choice(choices)
        env[row['name']] = val
    elif kind == 'decimal':
        lo, hi = _num(row, 'min', 'from'), _num(row, 'max', 'to')
        places = _places(row)
        val = round(rng.uniform(lo, hi), places)
        env[row['name']] = int(val) if places == 0 else val
    elif kind == 'imaginary':
        choices = [v for v in _whole_range(row) if v != 0]
        env[row['name']] = complex(0, rng.choice(choices))
    elif kind == 'complex':
        real = rng.choice(_whole_range(row))
        imag = rng.choice([v for v in _whole_range(_imag_row(row)) if v != 0])
        env[row['name']] = complex(real, imag)
    elif kind == 'list':
        items = _items(row)
        n = _pick_n(row)
        picked = rng.sample(items, n)
        for col, name in enumerate(row_names(row)):
            env[name] = picked[0][col]
            if n > 1:
                for i, item in enumerate(picked, 1):
                    env['{}{}'.format(name, i)] = item[col]


def calc_order(values):
    """Calculated values in an order where each only uses earlier ones."""
    calcs = {r['name']: names_in(parse_expr(r.get('formula') or '')) for r in values if r.get('kind') == 'calc'}
    order = []
    while calcs:
        #ready once it no longer uses any calculated value still waiting (itself included)
        ready = [n for n, deps in calcs.items() if not deps & set(calcs)]
        if not ready:
            raise FriendlyError('These calculated values depend on each other in a loop: {}.'
                                .format(', '.join(sorted(calcs))))
        for n in ready:
            order.append(n)
            del calcs[n]
    return order


def start_env(complex_ok=False):
    """A fresh set of values; with complex numbers on, i means sqrt(-1)."""
    return {COMPLEX: True, 'i': 1j} if complex_ok else {}


def draw_values(values, rng=None, complex_ok=False):
    """Pick one random set of values, honoring every "different from" rule."""
    rng = rng or random.Random()
    rows = {r['name']: r for r in values if r.get('kind') == 'calc'}
    order = calc_order(values)
    for _ in range(MAX_TRIES):
        env = start_env(complex_ok)
        for row in values:
            _draw(row, env, rng)
        if env.get(COMPLEX) and any('i' in row_names(r) for r in values):
            pass  # the teacher's own value called i wins
        for name in order:
            env[name] = evaluate(rows[name]['formula'], env)
        if all(env[row_names(row)[0]] != env[other]
               for row in values
               for other in (row.get('different_from') or []) if other in env):
            return env
    raise FriendlyError('I couldn\'t find values that are all different after {} tries. '
                        'Try wider ranges or fewer "different from" rules.'.format(MAX_TRIES))


# ---------------------------------------------------------------- text

def _placeholder(inner, env):
    """Value for one [..] placeholder, or None to leave the brackets alone."""
    try:
        tree = parse_expr(inner)
    except FriendlyError:
        return None
    used = names_in(tree)
    if not used or not used <= set(env):
        return None
    return format_num(evaluate(tree, env))


def fill(text, env):
    """Replace [name] and [formula] placeholders with drawn values."""
    def repl(mo):
        val = _placeholder(mo.group(1), env)
        return mo.group(0) if val is None else val
    return PLACEHOLDER_PATT.sub(repl, text or '')


def fill_question(text, env):
    return tidy(fill(text, env))


def _split_top(text):
    """Split on commas that aren't inside ( ), so min(a, b) stays whole."""
    parts, depth, start = [], 0, 0
    for pos, ch in enumerate(text):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ',' and depth == 0:
            parts.append(text[start:pos])
            start = pos + 1
    parts.append(text[start:])
    return parts


def _wraps_all(text):
    """True when text is (...) with the first ( closed by the last )."""
    if not (text.startswith('(') and text.endswith(')')):
        return False
    depth = 0
    for pos, ch in enumerate(text):
        depth += {'(': 1, ')': -1}.get(ch, 0)
        if depth == 0:
            return pos == len(text) - 1
    return False


def split_list(expr):
    """A list answer like 'x, y' or '(x, y)' -> (['x', 'y'], wrapped).
    A single formula comes back as a one-item list."""
    text = (expr or '').strip()
    parts = _split_top(text)
    if len(parts) == 1 and _wraps_all(text):
        inner = _split_top(text[1:-1])
        if len(inner) > 1:
            return [p.strip() for p in inner], True
    return [p.strip() for p in parts], False


def fill_answer(expr, env):
    """A numeric answer is a formula, a list of formulas like 'x, y' or
    '(x, y)', or text with placeholders."""
    if '[' in (expr or ''):
        #sqrt([a]), pi * [r]^2: worked out as a formula, [a] meaning the value a
        #(not filled in as text: "sqrt(3)" would be read as the number 3)
        parts, wrapped = split_list(expr)
        try:
            text = ', '.join(format_num(evaluate(PLACEHOLDER_PATT.sub(r'(\1)', p), env)) for p in parts)
        except Exception:
            return fill(expr, env)  # not all math, e.g. "[a] mph"
        return '({})'.format(text) if wrapped else text
    parts, wrapped = split_list(expr)
    if len(parts) == 1:
        return format_num(evaluate(expr, env))
    text = ', '.join(format_num(evaluate(p, env)) for p in parts)
    return '({})'.format(text) if wrapped else text


def worked_answer(text):
    """A saved Numeric answer as plain numbers: "sqrt(3), -sqrt(3)" -> "1.7321, -1.7321".
    (Answers saved before formulas with [values] were worked out kept the formula.)
    Anything that isn't all math comes back unchanged."""
    if not text or not re.search(r'[A-Za-z√π^*+]|\d\s*[-/]', text):
        return text
    parts, wrapped = split_list(text)
    try:
        [float(p) for p in parts]
        return text  # already plain numbers (e.g. 2.5e-05)
    except ValueError:
        pass
    try:
        nums = ', '.join(format_num(evaluate(p, {})) for p in parts)
    except Exception:
        return text
    return '({})'.format(nums) if wrapped else nums


# ---------------------------------------------------------------- checking

def _suggest(name, known):
    close = get_close_matches(name, known, n=1)
    return ' Did you mean "{}"?'.format(close[0]) if close else ''


def check_text(label, text, known):
    """Errors for placeholders in a piece of text that use unknown names."""
    errors = []
    for inner in PLACEHOLDER_PATT.findall(text or ''):
        try:
            tree = parse_expr(inner)
        except FriendlyError:
            continue  # not math, e.g. [0, 5]: shown as typed
        used = names_in(tree)
        missing = sorted(used - set(known))
        single = isinstance(tree.body, ast.Name)
        if missing and (single or used & set(known)):
            for name in missing:
                msg = ('The {} uses "{}", which isn\'t in your values table.{}'
                       .format(label, name, _suggest(name, known)))
                if msg not in errors:
                    errors.append(msg)
    return errors


def validate_values(values):
    """Plain-language errors for the values table; empty list if all good."""
    errors, seen = [], []
    for row in values:
        name = (row.get('name') or '').strip()
        if not name:
            errors.append('Every value needs a name.')
            continue
        bad = [n for n in row_names(row) if not NAME_PATT.match(n)]
        if bad:
            errors.append('"{}" can\'t be a name: use letters and numbers only, starting with a letter.'
                          .format(bad[0] or name))
            continue
        for part in row_names(row):
            if part in FUNCS:
                errors.append('"{}" is already used for math; please pick another name.'.format(part))
            if part in seen:
                errors.append('The name "{}" is used twice.'.format(part))
        try:
            seen.extend(pick_names(row))
        except FriendlyError:
            seen.extend(row_names(row))
        kind = row.get('kind')
        try:
            if kind == 'whole':
                _whole_range(row)
            elif kind == 'decimal':
                lo, hi = _num(row, 'min', 'from'), _num(row, 'max', 'to')
                if lo > hi:
                    raise FriendlyError('For {}, "from" ({}) must not be bigger than "to" ({}).'
                                        .format(name, format_num(lo), format_num(hi)))
                if not 0 <= _places(row) <= 6:
                    raise FriendlyError('For {}, decimal places must be between 0 and 6.'.format(name))
            elif kind == 'list':
                items, n = _items(row), _pick_n(row)
                if not items:
                    raise FriendlyError('The list for {} is empty.'.format(name))
                if n < 1 or n > len(items):
                    raise FriendlyError('{} picks {} from a list of only {}.'.format(name, n, len(items)))
            elif kind == 'imaginary':
                if not [v for v in _whole_range(row) if v != 0]:
                    raise FriendlyError('For {}, the range must include a number other than 0.'.format(name))
            elif kind == 'complex':
                _whole_range(row)
                if not [v for v in _whole_range(_imag_row(row)) if v != 0]:
                    raise FriendlyError('For {}, the imaginary part must be able to be something other than 0.'.format(name))
            elif kind == 'calc':
                if not (row.get('formula') or '').strip():
                    raise FriendlyError('Please give a formula for {}.'.format(name))
                parse_expr(row['formula'])
            else:
                raise FriendlyError('Please choose a kind for {}.'.format(name))
        except FriendlyError as exc:
            errors.append(str(exc))
    for row in values:
        if row.get('kind') == 'calc' and (row.get('formula') or '').strip():
            try:
                for used in sorted(names_in(parse_expr(row['formula'])) - set(seen)):
                    errors.append('{} uses "{}", which isn\'t defined.{}'
                                  .format(row.get('name'), used, _suggest(used, seen)))
            except FriendlyError:
                pass
        for other in row.get('different_from') or []:
            if other not in seen:
                errors.append('{} should be different from "{}", which isn\'t defined.{}'
                              .format(row.get('name'), other, _suggest(other, seen)))
    if not errors:
        try:
            calc_order(values)
        except FriendlyError as exc:
            errors.append(str(exc))
    return errors


def known_names(values):
    names = []
    for row in values:
        if row.get('name'):
            try:
                names.extend(pick_names(row))
            except FriendlyError:
                names.extend(row_names(row))
    return names


def _choices_of(row):
    """Every value a row can take, or None when there are too many to list (decimals)."""
    kind = row.get('kind')
    if kind == 'whole':
        rng = _whole_range(row)
        return None if len(rng) > 500 else [v for v in rng if not (row.get('nonzero') and v == 0)]
    if kind == 'list' and _pick_n(row) == 1:
        return _items(row)
    if kind == 'imaginary':
        return [complex(0, v) for v in _whole_range(row) if v != 0]
    if kind == 'complex':
        reals, imags = _whole_range(row), [v for v in _whole_range(_imag_row(row)) if v != 0]
        if len(reals) * len(imags) > 2000:
            return None
        return [complex(a, b) for a in reals for b in imags]
    return None


def every_env(values, limit=5000, complex_ok=False):
    """Every possible set of values, when there are at most `limit` of them; else None."""
    rows = [r for r in values if r.get('kind') != 'calc']
    options = [_choices_of(r) for r in rows]
    if any(o is None for o in options):
        return None
    total = 1
    for o in options:
        total *= max(1, len(o))
        if total > limit:
            return None
    calcs = {r['name']: r for r in values if r.get('kind') == 'calc'}
    order = calc_order(values)
    envs = []
    for combo in itertools.product(*options):
        env = start_env(complex_ok)
        for row, val in zip(rows, combo):
            if row.get('kind') == 'list':
                for col, name in enumerate(row_names(row)):
                    env[name] = val[col]
            else:
                env[row['name']] = val
        if not all(env.get(row_names(r)[0]) != env.get(o) for r in rows for o in r.get('different_from') or [] if o in env):
            continue
        for name in order:
            env[name] = evaluate(calcs[name]['formula'], env)
        #calculated values can have "different from" rules too
        if all(env[row_names(r)[0]] != env[o] for r in values for o in r.get('different_from') or [] if o in env):
            envs.append(env)
    return envs


def try_draws(values, render, times=300, complex_ok=False):
    """Before a problem is saved, run it on every possible set of values (or,
    when there are too many, on a few hundred random ones) so that dividing
    by zero or impossible rules are caught now, not when a student opens it."""
    envs = every_env(values, complex_ok=complex_ok)
    if envs is not None:
        if not envs and values:
            raise FriendlyError('No set of values satisfies all the "different from" rules.')
        for env in envs or [start_env(complex_ok)]:
            render(env)
        return
    rng = random.Random(0)
    for _ in range(times):
        env = draw_values(values, rng, complex_ok)
        render(env)
