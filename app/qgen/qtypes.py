"""Question types.

Each type knows how to check a teacher's problem, turn it into one
student's concrete problem, draw the answer field, and grade the answer.
To add a type, subclass QType and add it to REGISTRY.

A problem is described by plain data so the same code serves the saved
problem, the "Show me 3 examples" preview, and the AI helper:

    question  text with [name] placeholders (or legacy {{...}} markup)
    answer    meaning depends on the type (formula, accepted answers, ...)
    options   dict: values, choices, shuffle, show_n, case_sensitive,
              grading_notes, markup, images ([{file, label}], one picked
              at random per student; its label is [picture])
"""
import json
import random
import re

from wtforms import StringField, TextAreaField, RadioField, SelectMultipleField
from wtforms.widgets import ListWidget, CheckboxInput

from . import friendly as F
from .probspec import process_spec


def is_legacy(question, options):
    if options.get('markup'):
        return options['markup'] == 'legacy'
    return '{{' in (question or '')


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
    """Several checkboxes; any number may be ticked."""
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


# ---------------------------------------------------------------- grading helpers

def numbers_match(subm, corr):
    """Every number in the answer must match within 1% (or 0.01 near zero).
    Order doesn't matter, so '3, 5' matches '5, 3'."""
    if subm in (None, '', 'None'):
        return False
    numpatt = r'-?\d*\.?\d+'
    sublst = sorted(float(n) for n in re.findall(numpatt, subm))
    corlst = sorted(float(n) for n in re.findall(numpatt, corr))
    if not corlst or len(sublst) != len(corlst):
        return False
    for got, want in zip(sublst, corlst):
        if abs(want) >= 1:
            if abs(got - want) > 0.01:
                return False
        elif want == 0:
            if abs(got) >= 0.01:
                return False
        elif abs(got - want) / abs(want) > 0.01:
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
    answer_label = 'Answer'
    answer_help = ''
    uses_choices = False

    def validate(self, question, answer, options):
        """Plain-language errors for this problem; empty if it's ready."""
        if not (question or '').strip():
            return ['Please write the question.']
        if is_legacy(question, options):
            return self.validate_legacy(question, answer, options)
        values = options.get('values') or []
        errors = F.validate_values(values)
        known = F.known_names(values)
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
                F.try_draws(values, run)
            except F.FriendlyError as exc:
                errors.append(str(exc))
        return errors

    def validate_legacy(self, question, answer, options):
        return ['Old-style {{...}} markup only works with Numeric questions.']

    def validate_parts(self, answer, options, known):
        return []

    def instantiate(self, question, answer, options, rng=None):
        """One student's version: (question text, correct answer, extra data)."""
        rng = rng or random.Random()
        picture = pick_picture(options, rng)
        if is_legacy(question, options):
            prob, ansr = process_spec(question, answer or '')
            opts = {}
        else:
            env = F.draw_values(options.get('values') or [], rng)
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
    answer_help = 'Example: speed * hours. For several numbers use placeholders: [x], [y]'

    def validate_legacy(self, question, answer, options):
        try:
            for _ in range(5):
                process_spec(question, answer or '')
        except Exception as exc:
            return ['The old-style markup has a problem: {}'.format(exc)]
        return []

    def validate_parts(self, answer, options, known):
        if not (answer or '').strip():
            return ['Please give the answer formula.']
        if '[' in answer:
            return F.check_text('answer', answer, known)
        try:
            tree = F.parse_expr(answer)
        except F.FriendlyError as exc:
            return [str(exc)]
        return ['The answer uses "{}", which isn\'t in your values table.{}'
                .format(n, F._suggest(n, known)) for n in sorted(F.names_in(tree) - set(known))]

    def render_answer(self, answer, env):
        return F.fill_answer(answer, env)

    def grade(self, stored, conc_ansr, conc_opts, options):
        return 1.0 if numbers_match(stored, conc_ansr) else 0.0


class Text(QType):
    key = 'text'
    label = 'Short text'
    answer_label = 'Accepted answers (one per line)'
    answer_help = 'Any of these counts as correct. Capitals and extra spaces are ignored unless you tick "Case sensitive".'

    def validate_parts(self, answer, options, known):
        if not [a for a in (answer or '').splitlines() if a.strip()]:
            return ['Please give at least one accepted answer.']
        return F.check_text('answer', answer, known)

    def render_answer(self, answer, env):
        return '\n'.join(F.fill(a.strip(), env) for a in answer.splitlines() if a.strip())

    def grade(self, stored, conc_ansr, conc_opts, options):
        cs = bool(options.get('case_sensitive'))
        got = normalize_text(stored, cs)
        return 1.0 if got and any(got == normalize_text(a, cs) for a in conc_ansr.splitlines()) else 0.0

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
            nright = rng.randint(max(1, show_n - len(wrong)), min(show_n, len(right)))
        else:
            nright = 1
        return rng.sample(right, nright) + rng.sample(wrong, min(show_n - nright, len(wrong)))

    def render(self, question, answer, options, env, rng):
        filled = [(F.fill(text, env), ok) for text, ok in self.choice_lines(options)]
        #numeric distractors can land on the right answer; drop repeats
        merged = {}
        for text, ok in filled:
            merged[text] = merged.get(text, False) or ok
        picked = self.pick(list(merged.items()), options.get('show_n'), rng)
        if options.get('shuffle', True):
            rng.shuffle(picked)
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


class ChoiceMany(ChoiceOne):
    key = 'choice_many'
    label = 'Pick several'
    multi = True

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


def enumerate_choices(conc_opts):
    for i, text in enumerate(conc_opts.get('choices', [])):
        yield str(i), text


REGISTRY = {t.key: t for t in (Numeric(), Text(), ChoiceOne(), ChoiceMany(), TrueFalse(), Essay())}


def get_qtype(key):
    return REGISTRY.get(key or 'numeric', REGISTRY['numeric'])
