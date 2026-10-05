"""Live helper for teachers writing problems and building quizzes.

Quick rule-based checks (no AI) that run as the teacher types. Each hint:

    {'level': 'error' | 'warn' | 'tip', 'text': '...', 'action': {...} or None}

Actions are one-click fixes the page knows how to apply:
    {'type': 'add_value', 'name': 'hours', 'label': 'Add a value named hours'}
    {'type': 'set_qtype', 'value': 'truefalse', 'label': 'Switch to True / False'}
"""
import ast
import random
import re
from difflib import get_close_matches

from . import friendly as F
from .qtypes import get_qtype, parse_choices, picture_labels, PICTURE_NAME, uses_complex


def hint(level, text, action=None):
    return {'level': level, 'text': text, 'action': action}


def _names_used(texts):
    """Every name used inside [..] placeholders or plain formulas."""
    used = set()
    for text in texts:
        for inner in F.PLACEHOLDER_PATT.findall(text or ''):
            try:
                used |= F.names_in(F.parse_expr(inner))
            except F.FriendlyError:
                pass
    return used


def _formula_names(expr):
    try:
        return F.names_in(F.parse_expr(expr))
    except F.FriendlyError:
        return set()


def _switch(qtype, text):
    return {'type': 'set_qtype', 'value': qtype, 'label': text}


def variety(qt, question, answer, options, draws=60):
    """Rough count of different versions students can get, and the answer if
    it never changes. Sampling, not exact: a problem with thousands of
    versions just shows as "many"."""
    rng = random.Random(7)
    versions, answers = set(), set()
    try:
        for _ in range(draws):
            prob, ansr, opts = qt.instantiate(question, answer, options, rng)
            versions.add((prob, opts.get('image'), tuple(opts.get('choices') or ())))
            answers.add(ansr)
    except F.FriendlyError:
        return draws, None
    return len(versions), (next(iter(answers)) if len(answers) == 1 else None)


def problem_hints(qtype_key, question, answer, options):
    qt = get_qtype(qtype_key)
    question, answer = question or '', answer or ''
    hints = []
    if not question.strip():
        return [hint('tip', 'Start by writing the question. Put a random value in square brackets, like [speed].')]

    values = options.get('values') or []
    known = F.known_names(values)
    if picture_labels(options):
        known.append(PICTURE_NAME)
    if uses_complex(options) and 'i' not in known:
        known.append('i')

    #errors, with a one-click fix for names that aren't defined yet
    missing = set()
    for text, label in [(question, 'question'), (answer, 'answer'), (options.get('choices') or '', 'choices')]:
        for inner in F.PLACEHOLDER_PATT.findall(text):
            try:
                used = F.names_in(F.parse_expr(inner))
            except F.FriendlyError:
                continue
            if isinstance(F.parse_expr(inner).body, ast.Name) or used & set(known):
                missing |= used - set(known)
    if qt.key == 'numeric' and answer.strip() and '[' not in answer:
        missing |= _formula_names(answer) - set(known)
    for name in sorted(missing):
        close = get_close_matches(name, known, n=1)
        text = '"{}" isn\'t in your values table.'.format(name)
        if close:
            text += ' Did you mean "{}"?'.format(close[0])
        hints.append(hint('error', text, {'type': 'add_value', 'name': name, 'label': 'Add a value named {}'.format(name)}))
    for err in qt.validate(question, answer, options):
        if not any('"{}"'.format(n) in err for n in missing):
            hints.append(hint('error', err))

    #values that are defined but never shown or used
    texts = [question, answer, options.get('choices') or '']
    used = _names_used(texts)
    if qt.key == 'numeric' and '[' not in answer:
        used |= _formula_names(answer)
    if qt.key == 'truefalse':
        try:
            used |= F.condition_names(answer)
        except F.FriendlyError:
            pass
    for row in values:
        if row.get('kind') == 'calc':
            used |= _formula_names(row.get('formula') or '')
        used |= set(row.get('different_from') or [])
    for row in values:
        name = row.get('name')
        try:
            numbered = set(F.pick_names(row))
        except F.FriendlyError:
            numbered = set()
        for part in F.row_names(row):
            #a column counts as used if it or any of its numbered copies (who1, who2...) appears
            copies = {n for n in numbered if n == part or re.fullmatch(re.escape(part) + r'\d+', n)}
            if part and not copies & used:
                hints.append(hint('warn', 'You made a value called "{}" but never use it. Put [{}] in the question, or remove it.'.format(part, part)))
        if row.get('kind') == 'whole' and str(row.get('min', '')).strip() and str(row.get('min')) == str(row.get('max')):
            hints.append(hint('warn', '"{}" goes from {} to {}, so it\'s always the same number.'.format(name, row['min'], row['max'])))
        if row.get('kind') == 'list' and len([i for i in str(row.get('items') or '').split(',') if i.strip()]) == 1:
            hints.append(hint('warn', 'The list for "{}" has only one item, so every student gets the same one.'.format(name)))

    #anti-copying: how many different versions can students get, and can answers be passed along?
    if not [h for h in hints if h['level'] == 'error'] and qt.key != 'essay':
        n, same_answer = variety(qt, question, answer, options)
        if n == 1:
            hints.append(hint('warn', 'Every student gets exactly the same question and answer, so answers can be passed along. '
                              'Add a random value (like [a]) or several pictures.'))
        elif n < 6:
            hints.append(hint('warn', 'Only about {} different versions are possible, so students sitting together will often get the same one. '
                              'Widen the ranges or add another value.'.format(n)))
        elif same_answer and qt.key in ('numeric', 'text', 'truefalse'):
            hints.append(hint('warn', 'The question changes, but the correct answer is the same for everyone ({}), so it can be passed along.'.format(same_answer)))
        if qt.key == 'truefalse' and (answer or '').strip().lower() in F.TRUE_WORDS | F.FALSE_WORDS and n > 1:
            hints.append(hint('tip', 'The answer is always {}. A comparison like a > b makes it true for some students and false for others.'
                              .format('True' if answer.strip().lower() in F.TRUE_WORDS else 'False')))
    if qt.uses_choices and options.get('shuffle') is False:
        hints.append(hint('warn', 'Shuffling is off, so every student sees the choices in the same order and "it\'s the second one" can be passed along.'))

    #does the wording suggest a different question type?
    low = question.lower()
    if re.search(r'\btrue\s*(or|/)\s*false\b', low) and qt.key != 'truefalse':
        hints.append(hint('tip', 'This reads like a true-or-false question.', _switch('truefalse', 'Switch to True / False')))
    elif re.match(r'\s*(explain|describe|discuss|justify|why|compare|in your own words)\b', low) and qt.key != 'essay':
        hints.append(hint('tip', 'Questions that ask students to explain usually work best as a written answer that you grade.',
                          _switch('essay', 'Switch to Long text')))
    elif re.search(r'\b(select|choose|tick|check) all\b|\ball that apply\b', low) and qt.key != 'choice_many':
        hints.append(hint('tip', '"Select all" questions need Pick several, so students can check more than one.',
                          _switch('choice_many', 'Switch to Pick several')))
    if qt.key == 'choice_one' and len([c for c in parse_choices(options.get('choices')) if c[1]]) > 1 and not options.get('show_n'):
        hints.append(hint('tip', 'You marked more than one correct choice.', _switch('choice_many', 'Switch to Pick several')))
    if qt.key == 'numeric' and answer.strip() and '[' not in answer and not re.search(r'\d', answer) and not _formula_names(answer) & set(known):
        try:
            F.parse_expr(answer)
        except F.FriendlyError:
            hints.append(hint('tip', 'The answer looks like words, not a number.', _switch('text', 'Switch to Short text')))

    #choice lists
    if qt.uses_choices:
        lines = [t for t, _ in parse_choices(options.get('choices'))]
        dup = sorted({t for t in lines if lines.count(t) > 1})
        if dup:
            hints.append(hint('warn', 'These choices appear twice: {}.'.format(', '.join(dup))))

    #answers that come out with long decimals are hard to type
    if not [h for h in hints if h['level'] == 'error'] and qt.key == 'numeric':
        rng = random.Random(1)
        try:
            for _ in range(15):
                _, ansr, _ = qt.instantiate(question, answer, options, rng)
                if re.search(r'\d\.\d{3,}', ansr):
                    hints.append(hint('tip', 'Some answers come out like {}. Consider telling students how to round, and setting “How close must the answer be?” to match (e.g. 2 decimal places).'.format(ansr)))
                    break
        except F.FriendlyError:
            pass

    if qt.key == 'essay' and not (options.get('grading_notes') or answer).strip():
        hints.append(hint('tip', 'Consider adding grading notes or a model answer — they\'ll be shown to you while grading.'))
    if not [h for h in hints if h['level'] in ('error', 'warn')]:
        hints.insert(0, hint('ok', 'Looks good. Press “Show me 3 examples” to check what students will see.'))
    return hints


def quiz_hints(title, vpids, calculator_ok, existing_titles, problems, lay=None, shuffle_order=True):
    """problems: {id: VProblem} for the checked ids; lay: the quiz layout with groups."""
    from . import layout
    hints = []
    for err in layout.check(lay or []):
        hints.append(hint('error', err))
    if vpids and not shuffle_order:
        hints.append(hint('warn', 'Question order isn\'t shuffled, so every student has the same question 1, 2, 3… '
                          'and "number 3 is B" is easier to pass along.'))
    if not (title or '').strip():
        hints.append(hint('error', 'Give the quiz a title so students can recognise it.'))
    elif title.strip().lower() in existing_titles:
        hints.append(hint('warn', 'Another quiz is already called "{}". A different title avoids mix-ups.'.format(title.strip())))
    if not vpids:
        return hints + [hint('tip', 'Check the problems to include. They\'ll appear under “Questions in this quiz”.')]
    for pid in sorted({p for p in vpids if vpids.count(p) > 1}):
        p = problems.get(pid)
        hints.append(hint('tip', '"{}" is included {} times. Each copy gets different random values — fine if that\'s what you want.'
                          .format(p.title if p else pid, vpids.count(pid))))
    calc = [p for p in problems.values() if p.calculator_ok]
    if calc and not calculator_ok:
        hints.append(hint('tip', 'Students will have a calculator: {} {}.'.format(
            ', '.join('"{}"'.format(p.title) for p in calc), 'allows one' if len(calc) == 1 else 'allow one')))
    for p in problems.values():
        errors = get_qtype(p.qtype).validate(p.raw_prob, p.raw_ansr, p.options)
        if errors:
            hints.append(hint('warn', '"{}" has something to fix: {}'.format(p.title, errors[0])))
    cplx = [p for p in problems.values() if uses_complex(p.options)]
    if cplx and len(cplx) < len(problems):
        hints.append(hint('tip', 'Only some problems use complex numbers ({}). Fine if intended; the others will never show one.'
                          .format(', '.join('"{}"'.format(p.title) for p in cplx))))
    essays = [p for p in problems.values() if not get_qtype(p.qtype).auto_graded]
    if essays:
        hints.append(hint('tip', 'This quiz has {} written answer{}. Students see their score after you grade {} under Review.'.format(
            len(essays), '' if len(essays) == 1 else 's', 'it' if len(essays) == 1 else 'them')))
    kinds = {p.qtype for p in problems.values()}
    if len(vpids) >= 6 and len(kinds) == 1:
        only = get_qtype(next(iter(kinds))).label
        hints.append(hint('tip', 'All {} problems are {}. Mixing in another type can check understanding in a different way.'.format(len(vpids), only)))
    fixed = [p for p in problems.values() if not p.options.get('values')
             and get_qtype(p.qtype).key != 'essay' and len(p.options.get('images') or []) < 2]
    if fixed and len(fixed) == len(problems):
        hints.append(hint('tip', 'None of these problems has random values, so every student gets identical questions.'))
    if len(vpids) > 30:
        hints.append(hint('tip', '{} problems is a long quiz; consider splitting it.'.format(len(vpids))))
    if not [h for h in hints if h['level'] in ('error', 'warn')]:
        hints.insert(0, hint('ok', 'Looks good.'))
    return hints
