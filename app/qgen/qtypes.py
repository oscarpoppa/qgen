"""Question types.

Each type knows how to check a teacher's problem, turn it into one
student's concrete problem, draw the answer field, and grade the answer.
To add a type, subclass QType and add it to REGISTRY.

A problem is described by plain data so the same code serves the saved
problem, the "Show me 3 examples" preview, and the AI helper:

    question  text with [name] placeholders
    answer    meaning depends on the type (formula, accepted answers, ...)
    options   dict: values, choices, combos, shuffle, show_n, case_sensitive, precision, ordered,
              answer_display (Numeric: exact form shown on results), complex,
              grading_notes, markup ('friendly'), images ([{file, label}], one picked
              at random per student; its label is [picture])
"""
import ast
import json
import math
import random
import re
from decimal import Decimal, ROUND_HALF_UP

from wtforms import HiddenField, StringField, TextAreaField, RadioField, SelectMultipleField
from wtforms.widgets import ListWidget, CheckboxInput

from . import friendly as F


# ---------------------------------------------------------------- pictures

#a problem may list several pictures; each student's copy gets one at random,
#and its label can be used in the text and answer as [picture]
PICTURE_NAME = 'picture'


def pictures(options):
    return [p for p in (options.get('images') or []) if p.get('file')]


def picture_labels(options):
    """Labels, but only when some picture has one (otherwise [picture] is unused)."""
    labels = [(p.get('label') or '').strip() for p in pictures(options)]
    return labels if any(labels) else []


def pick_picture(options, rng):
    pics = pictures(options)
    return rng.choice(pics) if pics else None


# ---------------------------------------------------------------- fields

class OptionalRadioField(RadioField):
    """A radio group a student may leave blank (graded as wrong)."""
    def pre_validate(self, form):
        if self.data in (None, '', 'None'):
            return
        super().pre_validate(form)


class CheckboxField(SelectMultipleField):
    """Several checkboxes; any number may be checked."""
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


# ---------------------------------------------------------------- grading helpers

PRECISIONS = {
    'close': 'Within 0.01 (recommended)',
    'exact': 'Exactly',
    'hundredths': 'Rounded to 2 decimal places',
    'whole': 'Rounded to a whole number',
}

#a mixed number ("1 1/2"), a fraction ("3/4"), or a decimal ("-0.75", ".5")
_NUMBER = re.compile(r'(-?)\s*(?:(\d+)\s+(\d+)\s*/\s*(\d+)|(\d+)\s*/\s*(\d+)|(\d*\.?\d+))')


def read_numbers(text):
    """All the numbers a student typed, understanding fractions and mixed numbers."""
    out = []
    for sign, whole, num, den, fnum, fden, dec in _NUMBER.findall(text or ''):
        try:
            if whole:
                val = int(whole) + int(num) / int(den)
            elif fnum:
                val = int(fnum) / int(fden)
            else:
                val = float(dec)
        except ZeroDivisionError:
            continue
        out.append(-val if sign else val)
    return out


def school_round(x, places=0):
    """Round halves up (away from zero), the way it's taught: 6.5 -> 7."""
    q = Decimal(1).scaleb(-places)
    return float(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP))


def _close_enough(got, want, precision):
    if precision == 'whole':
        return abs(got - round(got)) < 1e-9 and round(got) == school_round(want)
    if precision == 'hundredths':
        return abs(got - school_round(want, 2)) < 0.0005
    if precision == 'exact':
        #answers are stored to 4 decimal places, so 1/3 matches 0.3333
        return abs(got - want) <= 0.00005 + 1e-9 * abs(want)
    #the original rule: within 0.01, or within 1% for numbers smaller than 1
    if abs(want) >= 1:
        return abs(got - want) <= 0.01
    if want == 0:
        return abs(got) < 0.01
    return abs(got - want) / abs(want) <= 0.01


#a student's answer with math in it (2√3, π/2, 2^0.5, (1+√5)/2), not just plain numbers
_MATHY = re.compile(r'[√π^*()×·÷]|sqrt|pi|\d\s*x\s*\d', re.I)
_REAL_MATH = re.compile(r'[√π^]|sqrt|pi', re.I)


def _student_expr(part):
    """A student's way of writing math -> a formula the calculator reads:
    2√3 -> 2*sqrt(3), √(x) -> sqrt(x), 2π -> 2*pi, (a)(b) -> (a)*(b), 6×2 or 6x2 -> 6*2."""
    e = part.strip().replace('−', '-').replace('π', 'pi').replace('√', 'sqrt')
    e = re.sub(r'(?<=\d)\s*[xX]\s*(?=\d)', '*', e)              # 6x2 (a times sign typed as x)
    e = re.sub(r'sqrt\s*(\d+(?:\.\d+)?|pi)', r'sqrt(\1)', e)    # √3 -> sqrt(3)
    e = re.sub(r'(\d|\)|pi)\s*(sqrt|pi|\()', r'\1*\2', e)       # 2√3, 2π, 2(…), )(
    e = re.sub(r'(\)|pi)\s*(\d)', r'\1*\2', e)                   # (…)2, π2
    return e


def student_numbers(text):
    """The numbers in a student's answer when it contains math, worked out
    ("2√3" -> "3.4641016151"), as a comma list; None when it's plain numbers
    (read as before, including 3/4 and 1 1/2); '' (never right) when it has
    √, π or ^ but can't be worked out."""
    if not text or not _MATHY.search(text):
        return None
    parts, _ = F.split_list(text)
    out = []
    for part in parts:
        try:
            value = F.evaluate(_student_expr(part), {'pi': math.pi})
        except (F.FriendlyError, KeyError, SyntaxError):
            value = None
        if value is None or isinstance(value, complex):
            #math that can't be worked out (√-4, √(x)) isn't read for its plain numbers
            #(that would turn √-4 into -4); only brackets/× around plain numbers fall back
            return '' if _REAL_MATH.search(text) else None
        #written out in full (never 1e-05), which the number reader understands
        out.append(format(float(value), '.10f').rstrip('0').rstrip('.') or '0')
    return ', '.join(out)


_PREC = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2, ast.Mod: 2, ast.Pow: 4}


def _latex(node):
    """A student's worked-out formula as math notation, built from the parsed formula
    (numbers, π, operations), never from what they typed, so nothing else can get in."""
    if isinstance(node, ast.Expression):
        return _latex(node.body)
    if isinstance(node, ast.Constant):
        return F.format_num(node.value)
    if isinstance(node, ast.Name):
        return '\\pi' if node.id == 'pi' else ''
    if isinstance(node, ast.UnaryOp):
        inner = _latex(node.operand)
        if isinstance(node.operand, ast.BinOp) and _PREC[type(node.operand.op)] < 4:
            inner = '\\left(' + inner + '\\right)'
        return ('-' if isinstance(node.op, ast.USub) else '') + inner
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [_latex(a) for a in node.args]
        if node.func.id == 'sqrt' and len(args) == 1:
            return '\\sqrt{' + args[0] + '}'
        if node.func.id == 'abs' and len(args) == 1:
            return '\\left|' + args[0] + '\\right|'
        return '\\operatorname{' + node.func.id + '}\\left(' + ', '.join(args) + '\\right)'
    if isinstance(node, ast.BinOp):
        op = type(node.op)
        if op is ast.Div:
            return '\\frac{' + _latex(node.left) + '}{' + _latex(node.right) + '}'

        def side(child, right=False):
            text = _latex(child)
            if isinstance(child, ast.BinOp) and type(child.op) is not ast.Div and (
                    _PREC[type(child.op)] < _PREC[op] or (right and _PREC[type(child.op)] == _PREC[op] and op in (ast.Sub, ast.Pow))):
                text = '\\left(' + text + '\\right)'
            return text
        if op is ast.Pow:
            return side(node.left) + '^{' + _latex(node.right) + '}'
        left, right = side(node.left), side(node.right, right=True)
        if op is ast.Mult:
            #2√3 and 2π read best without a dot; numbers side by side need one
            implicit = isinstance(node.left, ast.Constant) and (
                isinstance(node.right, (ast.Call, ast.Name)) or right.startswith('\\left('))
            return left + (' ' if implicit else ' \\cdot ') + right
        return left + {ast.Add: ' + ', ast.Sub: ' - ', ast.Mod: ' \\bmod '}[op] + right
    return ''


def student_math(text):
    """A student's math answer drawn as math, e.g. "2√3" -> "\\( 2\\sqrt{3} \\)";
    None when the answer is plain numbers or can't be worked out."""
    if student_numbers(text) in (None, ''):
        return None
    parts, wrapped = F.split_list(text)
    shown = [_latex(F.parse_expr(_student_expr(p))) for p in parts]
    body = ', '.join(shown)
    return '\\( ' + ('\\left(' + body + '\\right)' if wrapped else body) + ' \\)'


def numbers_match(subm, corr, precision='close', ordered=False):
    """Every number in the answer must match. Unless ordered, '3, 5' matches
    '5, 3'; ordered is for points like (3, 5). Fractions like 3/4 and 1 1/2
    are understood."""
    if subm in (None, '', 'None'):
        return False
    sublst = read_numbers(subm)
    corlst = read_numbers(corr)
    if not ordered:
        sublst, corlst = sorted(sublst), sorted(corlst)
    if not corlst or len(sublst) != len(corlst):
        return False
    return all(_close_enough(got, want, precision) for got, want in zip(sublst, corlst))


def uses_complex(options):
    """Complex numbers are allowed only when the teacher checked the box or chose
    an imaginary/complex value, so they never turn up in ordinary arithmetic."""
    return bool(options.get('complex')) or F.uses_complex(options.get('values') or [])


def read_complex(text):
    """Complex numbers a student typed, like "3+2i, 3-2i" or "-i" (j works too).
    Returns None if any part can't be read."""
    out = []
    for piece in re.split(r'[,;]|\band\b|\bor\b', (text or '').lower()):
        piece = piece.strip().replace('j', 'i').replace(' ', '')
        if not piece:
            continue
        if not re.fullmatch(r'[0-9i+\-*/.()]+', piece):
            return None
        try:
            val = F.evaluate(piece, F.start_env(True))
        except (F.FriendlyError, KeyError):
            return None
        out.append(complex(val))
    return out


def complex_match(subm, corr, precision='close', ordered=False):
    """Every complex number must match (real and imaginary parts each checked
    with the problem's precision); order matters only when ordered."""
    got, want = read_complex(subm), read_complex(corr)
    if not got or not want or len(got) != len(want):
        return False
    def same(g, w):
        return _close_enough(g.real, w.real, precision) and _close_enough(g.imag, w.imag, precision)
    if ordered:
        return all(same(g, w) for g, w in zip(got, want))
    unused = list(got)
    for w in want:
        for g in unused:
            if same(g, w):
                unused.remove(g)
                break
        else:
            return False
    return True


def normalize_text(text, case_sensitive=False):
    text = re.sub(r'\s+', ' ', (text or '').strip()).rstrip('.')
    return text if case_sensitive else text.casefold()


def parse_choices(text):
    """'*Right\\nWrong' -> [('Right', True), ('Wrong', False)]"""
    out = []
    for line in (text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('*'):
            out.append((line[1:].strip(), True))
        else:
            out.append((line, False))
    return out


# ---------------------------------------------------------------- base

class QType:
    key = ''
    label = ''
    auto_graded = True
    paper = False  # done on paper: no answer box, the teacher scores it
    answer_label = 'Answer'
    answer_help = ''
    uses_choices = False

    def validate(self, question, answer, options):
        """Plain-language errors for this problem; empty if it's ready."""
        if not (question or '').strip():
            return ['Please write the question.']
        values = options.get('values') or []
        errors = F.validate_values(values)
        known = F.known_names(values)
        complex_ok = uses_complex(options)
        if complex_ok and 'i' not in known:
            known = known + ['i']
        if picture_labels(options):
            if PICTURE_NAME in known:
                errors.append('"{}" is used by the picture labels; please rename that value.'.format(PICTURE_NAME))
            known = known + [PICTURE_NAME]
            if not all(picture_labels(options)):
                errors.append('Every picture needs a label, since the problem uses [picture].')
        errors += F.check_text('question', question, known)
        errors += self.validate_parts(answer, options, known)
        if not errors:
            #run it a few times to catch problems that only some values cause
            try:
                labels = picture_labels(options)
                def run(env):
                    for label in labels or [None]:
                        if label is not None:
                            env = dict(env, **{PICTURE_NAME: label})
                        self.render(question, answer, options, env, random.Random(0))
                F.try_draws(values, run, complex_ok=complex_ok)
            except F.FriendlyError as exc:
                errors.append(str(exc))
        return errors

    def validate_parts(self, answer, options, known):
        return []

    def instantiate(self, question, answer, options, rng=None):
        """One student's version: (question text, correct answer, extra data)."""
        rng = rng or random.Random()
        picture = pick_picture(options, rng)
        env = F.draw_values(options.get('values') or [], rng, uses_complex(options))
        if picture and picture.get('label'):
            env[PICTURE_NAME] = picture['label']
        prob, ansr, opts = self.render(question, answer, options, env, rng)
        if picture:
            opts = dict(opts, image=picture['file'])
        return prob, ansr, opts

    def render(self, question, answer, options, env, rng):
        return F.fill_question(question, env), self.render_answer(answer, env), {}

    def render_answer(self, answer, env):
        return F.fill(answer or '', env)

    def make_field(self, name, conc_opts):
        return StringField(name)

    def to_stored(self, data):
        """Field data -> the string saved in CProblem.submitted."""
        return '' if data in (None, 'None') else str(data)

    def is_blank(self, stored):
        return not (stored or '').strip()

    def grade(self, stored, conc_ansr, conc_opts, options):
        """Credit from 0 to 1, or None when an instructor must grade it."""
        raise NotImplementedError

    def show_submitted(self, stored, conc_opts):
        return stored or ''

    def show_correct(self, conc_ansr, conc_opts):
        return conc_ansr or ''


# ---------------------------------------------------------------- types

class Numeric(QType):
    key = 'numeric'
    label = 'Numeric'
    answer_label = 'Answer (a formula)'
    answer_help = 'Example: speed * hours. Use the buttons for roots, powers and π. For a pair or list, separate with commas: x, y'

    def validate_parts(self, answer, options, known):
        if not (answer or '').strip():
            return ['Please give the answer formula.']
        display_errors = F.check_text('exact form', options['answer_display'], known) \
            if (options.get('answer_display') or '').strip() else []
        if '[' in answer:
            return F.check_text('answer', answer, known) + display_errors
        parts, _ = F.split_list(answer)
        if len(parts) > 1 and not all(parts):
            return ['The answer has an empty spot between commas. For a pair, write it like: x, y']
        errors = []
        for part in parts:
            try:
                tree = F.parse_expr(part)
            except F.FriendlyError as exc:
                errors.append(str(exc))
                continue
            errors += ['The answer uses "{}", which isn\'t in your values table.{}'
                       .format(n, F._suggest(n, known)) for n in sorted(F.names_in(tree) - set(known))]
        return list(dict.fromkeys(errors + display_errors))

    def render_answer(self, answer, env):
        return F.fill_answer(answer, env)

    def render(self, question, answer, options, env, rng):
        prob, ansr, opts = super().render(question, answer, options, env, rng)
        if uses_complex(options):
            opts['complex'] = True  # the quiz page tells the student how to type i
        if (options.get('answer_display') or '').strip():
            #how results show the correct answer, e.g. \\( 2\\sqrt{[n]} \\), with this student's values
            opts['display'] = F.fill_question(options['answer_display'].strip(), env)
        return prob, ansr, opts

    def grade(self, stored, conc_ansr, conc_opts, options):
        precision = options.get('precision') or 'close'
        ordered = bool(options.get('ordered'))
        if uses_complex(options):
            return 1.0 if complex_match(stored, conc_ansr, precision, ordered) else 0.0
        #math the student typed (2√3, π/2) is worked out first; so is a saved answer like sqrt(3)
        worked = student_numbers(stored)
        return 1.0 if numbers_match(worked if worked is not None else stored, F.worked_answer(conc_ansr),
                                    precision, ordered) else 0.0

    def show_submitted(self, stored, conc_opts):
        worked = student_numbers(stored)
        if worked is None or (conc_opts or {}).get('complex'):
            return stored or ''
        if worked == '':
            return "{} (couldn't be worked out)".format(stored)
        shown = ', '.join(F.format_num(float(v)) for v in worked.split(', '))
        #drawn as real math (a full root sign), from the worked-out formula
        return '{}  (= {})'.format(student_math(stored) or stored, shown)

    def show_correct(self, conc_ansr, conc_opts):
        """With an exact form, e.g. \\( 2\\sqrt{3} \\), shown alongside the number."""
        display = (conc_opts or {}).get('display')
        if not (conc_opts or {}).get('complex'):
            conc_ansr = F.worked_answer(conc_ansr)  # never "sqrt(3)": students see 1.7321
        return '{}  (≈ {})'.format(display, conc_ansr) if display else (conc_ansr or '')


class Text(QType):
    key = 'text'
    label = 'Short text'
    answer_label = 'Accepted answers (one per line)'
    answer_help = 'Any of these counts as correct. Capitals and extra spaces are ignored unless you check "Case sensitive".'

    def validate_parts(self, answer, options, known):
        if not [a for a in (answer or '').splitlines() if a.strip()]:
            return ['Please give at least one accepted answer.']
        return F.check_text('answer', answer, known)

    def render_answer(self, answer, env):
        return '\n'.join(F.fill(a.strip(), env) for a in answer.splitlines() if a.strip())

    def grade(self, stored, conc_ansr, conc_opts, options):
        cs = bool(options.get('case_sensitive'))
        got = normalize_text(stored, cs)
        if not got:
            return 0.0
        answers = [normalize_text(a, cs) for a in conc_ansr.splitlines() if a.strip()]
        if got in answers:
            return 1.0
        #a right answer inside a longer one ("a brown horse" for "horse"): the teacher decides
        if any(re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)', got) for a in answers if a):
            return None
        #a labeled picture ("what animal is this?"): there are many ways to name what's in it,
        #so an answer that isn't the label goes to the teacher too, not straight to wrong
        if picture_labels(options or {}):
            return None
        return 0.0

    def show_correct(self, conc_ansr, conc_opts):
        return ' or '.join(a for a in conc_ansr.splitlines() if a)


class ChoiceOne(QType):
    key = 'choice_one'
    label = 'Pick one'
    uses_choices = True
    multi = False

    def choice_lines(self, options):
        return parse_choices(options.get('choices'))

    def validate_parts(self, answer, options, known):
        choices = self.choice_lines(options)
        errors = []
        if len(choices) < 2:
            errors.append('Please give at least two choices, one per line.')
        right = [c for c in choices if c[1]]
        wrong = [c for c in choices if not c[1]]
        if not right:
            errors.append('Mark the correct choice with a * at the start of its line.')
        show_n = options.get('show_n')
        if show_n:
            if show_n < 2 or show_n > len(choices):
                errors.append('"Show only" must be between 2 and the number of choices ({}).'.format(len(choices)))
            elif not self.multi and len(wrong) < show_n - 1:
                errors.append('To show {} choices you need at least {} wrong ones.'.format(show_n, show_n - 1))
        elif not self.multi and len(right) > 1:
            errors.append('Pick one questions can only have one choice marked with *, '
                          'unless you use "Show only" to pick one of them at random.')
        for text, _ in choices:
            errors += F.check_text('choice "{}"'.format(text), text, known)
        return errors

    def pick(self, choices, show_n, rng):
        right = [c for c in choices if c[1]]
        wrong = [c for c in choices if not c[1]]
        if not show_n:
            return choices
        #repeats may have been dropped, so never ask for more than exist
        show_n = min(show_n, len(choices))
        if self.multi:
            #at least one correct, and at least one wrong when there are any,
            #so "check them all" is never the answer by accident
            most = min(show_n - 1 if wrong else show_n, len(right))
            nright = rng.randint(max(1, show_n - len(wrong)), max(1, most))
        else:
            nright = 1
        return rng.sample(right, nright) + rng.sample(wrong, min(show_n - nright, len(wrong)))

    def render(self, question, answer, options, env, rng):
        filled = [(F.fill(text, env), ok) for text, ok in self.choice_lines(options)]
        #numeric distractors can land on the right answer; drop repeats
        merged = {}
        for text, ok in filled:
            merged[text] = merged.get(text, False) or ok
        pool = list(merged.items())
        picked = self.pick(pool, options.get('show_n'), rng)
        if options.get('shuffle', True):
            rng.shuffle(picked)
        else:
            #keep the teacher's order, so a pool's picks never put the right answer first
            picked.sort(key=pool.index)
        opts = {'choices': [t for t, _ in picked], 'correct': [i for i, (_, ok) in enumerate(picked) if ok]}
        return F.fill_question(question, env), '; '.join(t for t, ok in picked if ok), opts

    def make_field(self, name, conc_opts):
        return OptionalRadioField(name, choices=list(enumerate_choices(conc_opts)))

    def to_stored(self, data):
        if data in (None, '', 'None'):
            return json.dumps([])
        return json.dumps([int(data)])

    def picked(self, stored):
        try:
            return sorted(int(i) for i in json.loads(stored or '[]'))
        except (TypeError, ValueError):
            return []

    def is_blank(self, stored):
        return not self.picked(stored)

    def grade(self, stored, conc_ansr, conc_opts, options):
        return 1.0 if self.picked(stored) == sorted(conc_opts.get('correct', [])) else 0.0

    def show_submitted(self, stored, conc_opts):
        choices = conc_opts.get('choices', [])
        return '; '.join(choices[i] for i in self.picked(stored) if i < len(choices))


def parse_combos(text):
    """'[a], [b]\n[c], [d]' -> [['[a]', '[b]'], ['[c]', '[d]']]. Commas inside
    brackets (like min(a, b)) don't split."""
    combos = []
    for line in (text or '').splitlines():
        parts = [p.strip().lstrip('*').strip() for p in re.split(r',(?![^\[]*\])', line)]
        parts = [p for p in parts if p]
        if parts:
            combos.append(parts)
    return combos


class ChoiceMany(ChoiceOne):
    """Several boxes to check. The right answer is the set of * choices, and/or
    any of the teacher's "other correct combinations"."""
    key = 'choice_many'
    label = 'Pick several'
    multi = True

    def validate_parts(self, answer, options, known):
        combos = parse_combos(options.get('combos'))
        if not combos:
            return super().validate_parts(answer, options, known)
        choices = self.choice_lines(options)
        texts = [t for t, _ in choices]
        errors = []
        if len(choices) < 2:
            errors.append('Please give at least two choices, one per line.')
        for combo in combos:
            for item in combo:
                if item not in texts:
                    errors.append('The combination "{}" uses "{}", which isn\'t one of the choices. '
                                  'Write it exactly as in the choices list.'.format(', '.join(combo), item))
        show_n = options.get('show_n')
        if show_n:
            if show_n < 2 or show_n > len(choices):
                errors.append('"Show only" must be between 2 and the number of choices ({}).'.format(len(choices)))
            elif all(len(c) > show_n for c in self.answer_sets(choices, combos)):
                errors.append('Every correct combination has more than {} choices, so it can\'t be shown whole.'.format(show_n))
        for text in texts:
            errors += F.check_text('choice "{}"'.format(text), text, known)
        return errors

    def answer_sets(self, choices, combos):
        """Every correct set of raw choice lines: the * set (if any) plus combinations."""
        sets = [list(c) for c in combos]
        starred = [t for t, ok in choices if ok]
        if starred and starred not in sets:
            sets.insert(0, starred)
        return sets

    def render(self, question, answer, options, env, rng):
        combos = parse_combos(options.get('combos'))
        if not combos:
            return super().render(question, answer, options, env, rng)
        lines = self.choice_lines(options)
        filled = {t: F.fill(t, env) for t, _ in lines}
        #numeric choices can come out equal; keep each shown text once
        pool = list(dict.fromkeys(filled[t] for t, _ in lines))
        raw_sets = self.answer_sets(lines, combos)
        sets = [sorted(set(filled[t] for t in s)) for s in raw_sets]
        for raw, got in zip(raw_sets, sets):
            if len(got) < len(set(raw)):
                raise F.FriendlyError('With some values, the combination "{}" turns into the same answer twice ({}). '
                                      'Change the ranges or use "different from" so that can\'t happen.'
                                      .format(', '.join(raw), ', '.join(filled[t] for t in raw)))
        show_n = options.get('show_n')
        if show_n:
            show_n = min(show_n, len(pool))
            target = rng.choice([s for s in sets if len(s) <= show_n] or sets)
            rest = [t for t in pool if t not in target]
            shown = target + rng.sample(rest, max(0, min(show_n - len(target), len(rest))))
        else:
            shown = pool
        if options.get('shuffle', True):
            rng.shuffle(shown)
        else:
            shown.sort(key=pool.index)
        index = {t: i for i, t in enumerate(shown)}
        valid = [sorted(index[t] for t in s) for s in sets if all(t in index for t in s)]
        valid = [v for i, v in enumerate(valid) if v not in valid[:i]]
        opts = {'choices': shown, 'correct': valid[0], 'combos': valid}
        answer_text = ' or '.join(', '.join(shown[i] for i in v) for v in valid)
        return F.fill_question(question, env), answer_text, opts

    def grade(self, stored, conc_ansr, conc_opts, options):
        combos = conc_opts.get('combos') or [conc_opts.get('correct', [])]
        return 1.0 if self.picked(stored) in [sorted(c) for c in combos] else 0.0

    def make_field(self, name, conc_opts):
        return CheckboxField(name, choices=list(enumerate_choices(conc_opts)))

    def to_stored(self, data):
        return json.dumps(sorted(int(i) for i in (data or [])))


class TrueFalse(ChoiceOne):
    key = 'truefalse'
    label = 'True / False'
    uses_choices = False
    answer_label = 'Answer'
    answer_help = 'True or False, or a comparison that decides it, like: a > b'

    def validate_parts(self, answer, options, known):
        if not (answer or '').strip():
            return ['Please give the answer: True, False, or a comparison like a > b.']
        try:
            missing = sorted(F.condition_names(answer) - set(known))
        except F.FriendlyError as exc:
            return [str(exc)]
        return ['The answer uses "{}", which isn\'t in your values table.{}'
                .format(n, F._suggest(n, known)) for n in missing]

    def render(self, question, answer, options, env, rng):
        truth = F.evaluate_condition(answer, env)
        opts = {'choices': ['True', 'False'], 'correct': [0 if truth else 1]}
        return F.fill_question(question, env), 'True' if truth else 'False', opts


class Essay(QType):
    key = 'essay'
    label = 'Long text (instructor grades)'
    auto_graded = False
    answer_label = 'Model answer (optional, only you see it)'
    answer_help = 'Shown to you while grading, and on the finished transcript.'

    def validate_parts(self, answer, options, known):
        return F.check_text('model answer', answer, known)

    def make_field(self, name, conc_opts):
        return TextAreaField(name)

    def grade(self, stored, conc_ansr, conc_opts, options):
        return None


class PaperOnly(QType):
    """Done on paper (draw, circle, color in): the page is the problem's picture, the
    student has no answer box, and the teacher types the score from the paper."""
    key = 'paper'
    label = 'Paper only (done on paper; you grade it)'
    auto_graded = False
    paper = True
    answer_label = 'Answer key (optional, only you see it)'
    answer_help = 'Shown to you while grading.'

    def validate(self, question, answer, options):
        #the page may say it all (a flower to color): no question needed
        if not (question or '').strip():
            return self.validate_parts(answer, options, F.known_names(options.get('values') or []))
        return super().validate(question, answer, options)

    def validate_parts(self, answer, options, known):
        errors = [] if options.get('images') else ['A Paper only problem needs its page in the picture section.']
        return errors + F.check_text('answer key', answer, known)

    def make_field(self, name, conc_opts):
        return HiddenField(name)

    def to_stored(self, data):
        return ''

    def is_blank(self, stored):
        return False  # never "left blank": the work is on paper, so it always waits for a grade

    def grade(self, stored, conc_ansr, conc_opts, options):
        return None


def enumerate_choices(conc_opts):
    for i, text in enumerate(conc_opts.get('choices', [])):
        yield str(i), text


REGISTRY = {t.key: t for t in (Numeric(), Text(), ChoiceOne(), ChoiceMany(), TrueFalse(), Essay(), PaperOnly())}


def get_qtype(key):
    return REGISTRY.get(key or 'numeric', REGISTRY['numeric'])
