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
import itertools
import math
import operator
import random
import re
from difflib import get_close_matches

from .probspec import tidy

KINDS = {
    'whole': 'Whole number',
    'decimal': 'Decimal',
    'list': 'Pick from list',
    'calc': 'Calculated',
}

FUNCS = {
    'sqrt': math.sqrt,
    'abs': abs,
    'round': round,
    'min': min,
    'max': max,
}

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
    """Accept the symbols people actually type: ^ for powers, x-like signs."""
    return (expr.replace('^', '**').replace('×', '*').replace('÷', '/')
                .replace('−', '-').replace('·', '*').strip())


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
                            'sqrt, abs, round, min, max.'.format(expr))
    return tree


def names_in(tree):
    """Value names used by a parsed formula (function names excluded)."""
    funcs = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - funcs


def _eval(node, env):
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
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
        return FUNCS[node.func.id](*args)
    raise FriendlyError('Unsupported formula.')


def evaluate(expr, env):
    """Evaluate a formula against the drawn values.

    A formula that is just one name returns that value as-is, so words
    from a pick-list work in placeholders.
    """
    tree = expr if isinstance(expr, ast.Expression) else parse_expr(expr)
    if isinstance(tree.body, ast.Name):
        return env[tree.body.id]
    for name in names_in(tree):
        if not isinstance(env[name], (int, float)):
            raise FriendlyError('"{}" is a word, so it can\'t be used in math.'.format(name))
    try:
        result = _eval(tree, env)
    except FriendlyError:
        raise
    except ZeroDivisionError:
        raise FriendlyError('"{}" divides by zero for some values.'.format(_show(expr)))
    except (ValueError, OverflowError, TypeError):
        raise FriendlyError('"{}" can\'t be worked out for some values (for example, the square root of a negative number).'.format(_show(expr)))
    #e.g. (-8) ^ (1/3) gives a complex number; huge results become infinity
    if isinstance(result, complex) or (isinstance(result, float) and not math.isfinite(result)):
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
    return all(_COMPARE[op](evaluate(left, env), evaluate(right, env)) for left, op, right in payload)


def format_num(val):
    """Show numbers the way a person would write them."""
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


def draw_values(values, rng=None):
    """Pick one random set of values, honoring every "different from" rule."""
    rng = rng or random.Random()
    rows = {r['name']: r for r in values if r.get('kind') == 'calc'}
    order = calc_order(values)
    for _ in range(MAX_TRIES):
        env = {}
        for row in values:
            _draw(row, env, rng)
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


def fill_answer(expr, env):
    """A numeric answer is either a plain formula or text with placeholders."""
    if '[' in (expr or ''):
        return fill(expr, env)
    return format_num(evaluate(expr, env))


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
    return None


def every_env(values, limit=5000):
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
        env = {}
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


def try_draws(values, render, times=300):
    """Before a problem is saved, run it on every possible set of values (or,
    when there are too many, on a few hundred random ones) so that dividing
    by zero or impossible rules are caught now, not when a student opens it."""
    envs = every_env(values)
    if envs is not None:
        if not envs and values:
            raise FriendlyError('No set of values satisfies all the "different from" rules.')
        for env in envs or [{}]:
            render(env)
        return
    rng = random.Random(0)
    for _ in range(times):
        env = draw_values(values, rng)
        render(env)
