""""Fill in for me": turn a teacher's plain-English description into the
problem form, using Claude.

The model only proposes form contents. Everything it returns goes through
the same checks as hand-typed input (friendly.validate_values and the
question type's validate) and lands in the form unsaved; students never
trigger a call, and quiz randomizing never depends on it.
"""
import json

import anthropic

from .friendly import KINDS
from .qtypes import REGISTRY, get_qtype

MODEL = 'claude-opus-5'
HOURLY_LIMIT = 30

_NULLABLE_STR = {'type': ['string', 'null']}

VALUE_SCHEMA = {
    'type': 'object',
    'properties': {
        'name': {'type': 'string'},
        'kind': {'type': 'string', 'enum': list(KINDS)},
        'min': _NULLABLE_STR,
        'max': _NULLABLE_STR,
        'step': _NULLABLE_STR,
        'places': _NULLABLE_STR,
        'nonzero': {'type': 'boolean'},
        'items': _NULLABLE_STR,
        'pick_n': _NULLABLE_STR,
        'formula': _NULLABLE_STR,
        'different_from': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['name', 'kind', 'min', 'max', 'step', 'places', 'nonzero', 'items', 'pick_n', 'formula', 'different_from'],
    'additionalProperties': False,
}

VALUES_ONLY_SCHEMA = {
    'type': 'object',
    'properties': {
        'values': {'type': 'array', 'items': VALUE_SCHEMA},
        'cannot_do': _NULLABLE_STR,
    },
    'required': ['values', 'cannot_do'],
    'additionalProperties': False,
}

PROBLEM_SCHEMA = {
    'type': 'object',
    'properties': {
        'qtype': {'type': 'string', 'enum': list(REGISTRY)},
        'title': {'type': 'string'},
        'question': {'type': 'string'},
        'values': {'type': 'array', 'items': VALUE_SCHEMA},
        'answer': _NULLABLE_STR,
        'choices': _NULLABLE_STR,
        'combos': _NULLABLE_STR,
        'show_n': {'type': ['integer', 'null']},
        'case_sensitive': {'type': 'boolean'},
        'grading_notes': _NULLABLE_STR,
        'cannot_do': _NULLABLE_STR,
    },
    'required': ['qtype', 'title', 'question', 'values', 'answer', 'choices', 'combos', 'show_n',
                 'case_sensitive', 'grading_notes', 'cannot_do'],
    'additionalProperties': False,
}

SYSTEM_PROMPT = """You help teachers write quiz problems for a quiz app. You turn the teacher's plain-English description into the app's problem form. A program, not you, later draws the random values separately for each student, so you only describe the rules.

# Random values
Each value has a name (letters and digits, starting with a letter, e.g. speed, a, who) and a kind:
- "whole": a whole number. min and max (inclusive, as strings like "3"), optional step ("5" gives 40, 45, 50...), optional nonzero true to skip 0.
- "decimal": min, max, and places (decimal places, "0" to "6"; default "1").
- "list": items is a comma-separated list, e.g. "Maria, Ahmed, Li" or "2, 3, 5, 7". Optional pick_n ("2") picks that many different items, available as name1, name2, ... (and name is the first).
- "calc": formula computed from other values, e.g. "speed * hours".
Any value may list other value names in different_from, e.g. b different from a.
Fields that don't apply to the kind must be null (nonzero false, different_from []).

# Placeholders and math
In the question, answers, and choices, [name] is replaced by a value and [formula] by its result, e.g. [a + b]. Formulas may use + - * / ^ ( ) and sqrt, abs, round(x, 2), min, max. Brackets that don't contain a defined name are shown as typed.

# Question types (qtype)
- "numeric": answer is a formula such as "speed * hours" (no brackets), or placeholders like "[x], [y]" when there are several numbers.
- "text": answer lists accepted answers, one per line. case_sensitive is usually false.
- "choice_one": choices, one per line, correct one starts with *. Example: "*[a + b]\\n[a + b + 1]\\n[a * b]". Optionally show_n to show only that many (needs enough wrong choices).
- "choice_many": like choice_one but several choices start with *. If different sets of ticks can each be right (e.g. "tick two numbers that add to 10"), leave the * off and list each acceptable set in combos, one per line, choices separated by commas and written exactly as in choices, e.g. "[a], [10 - a]\n[b], [10 - b]". combos is null otherwise.
- "truefalse": answer is True, False, or a comparison that decides it, like "a > b" or "a = b and b < 10".
- "essay": students write freely and a teacher grades it. answer may be a short model answer; grading_notes may hold marking guidance.
Unused fields are null (choices null unless a choice type; show_n null unless asked).

# Examples
"all integers from 3 to 5, then a random one of those" -> one value: name "n", kind "whole", min "3", max "5".
"two different numbers under 20" -> a: whole 1..19; b: whole 1..19, different_from ["a"].
"a price between $2 and $20 in 25-cent steps" -> quarters: whole min "8" max "80"; price: calc formula "quarters / 4".
"a random first name" -> who: list items "Maria, Ahmed, Li, Sam, Priya, Diego".

# Rules
- Follow the teacher's wording exactly; choose sensible names.
- Never invent kinds or fields. If part of the request can't be expressed with these kinds (for example "prime numbers only" with no list given), do the rest and explain the missing part briefly in cannot_do, in plain words for a teacher, suggesting a workaround (such as a "list" of the allowed numbers). Otherwise cannot_do is null.
- Values can come in matched pairs: a "list" named "country = capital" with items "France = Paris, Japan = Tokyo"; then [country] and [capital] always match.
- Keep the question text natural and student-facing. Math may use LaTeX between \\( and \\).
"""


class AIError(Exception):
    """A problem to show the teacher, in plain words."""


def _client(api_key):
    return anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=90.0)


def ask(api_key, kind, text, client=None):
    """Send one description to Claude. Returns (fill dict, usage dict)."""
    schema = PROBLEM_SCHEMA if kind == 'problem' else VALUES_ONLY_SCHEMA
    ask_for = ('Fill in the whole problem form for this description:' if kind == 'problem'
               else 'Fill in only the random values for this description:')
    client = client or _client(api_key)
    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={'type': 'adaptive'},
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
            system=[{'type': 'text', 'text': SYSTEM_PROMPT, 'cache_control': {'type': 'ephemeral'}}],
            messages=[{'role': 'user', 'content': '{}\n\n{}'.format(ask_for, text)}],
            output_config={'format': {'type': 'json_schema', 'schema': schema}},
        )
    except anthropic.AuthenticationError:
        raise AIError('The AI helper\'s API key isn\'t working. Please ask your administrator to check it.')
    except anthropic.RateLimitError:
        raise AIError('The AI helper is busy. Please try again in a minute.')
    except anthropic.APIStatusError as exc:
        if exc.status_code >= 500:
            raise AIError('The AI helper is having trouble right now. Please try again in a few minutes.')
        raise AIError('The AI helper couldn\'t handle that request.')
    except anthropic.APIConnectionError:
        raise AIError('Couldn\'t reach the AI helper. Please check the internet connection and try again.')
    usage = {'input_tokens': getattr(resp.usage, 'input_tokens', None),
             'output_tokens': getattr(resp.usage, 'output_tokens', None)}
    if resp.stop_reason == 'refusal':
        raise AIError('The AI helper declined that request. Please rephrase it, or fill in the form yourself.')
    if resp.stop_reason == 'max_tokens':
        raise AIError('That description was too long for the AI helper. Please shorten it.')
    text_out = next((b.text for b in resp.content if b.type == 'text'), None)
    try:
        fill = json.loads(text_out or '')
    except ValueError:
        raise AIError('The AI helper gave an answer I couldn\'t read. Please try again.')
    return clean(fill, kind), usage


def clean(fill, kind):
    """Keep only known fields, as strings the form understands."""
    values = []
    for v in fill.get('values') or []:
        row = {'name': str(v.get('name') or ''), 'kind': v.get('kind') if v.get('kind') in KINDS else ''}
        for key in ('min', 'max', 'step', 'places', 'items', 'pick_n', 'formula'):
            if v.get(key) not in (None, ''):
                row[key] = str(v[key])
        if v.get('nonzero'):
            row['nonzero'] = True
        diff = [str(d) for d in (v.get('different_from') or []) if d]
        if diff:
            row['different_from'] = diff
        values.append(row)
    out = {'values': values, 'cannot_do': fill.get('cannot_do') or None}
    if kind == 'problem':
        out.update(
            qtype=fill.get('qtype') if fill.get('qtype') in REGISTRY else 'numeric',
            title=str(fill.get('title') or '')[:64],
            question=str(fill.get('question') or ''),
            answer=str(fill.get('answer') or ''),
            choices=str(fill.get('choices') or ''),
            combos=str(fill.get('combos') or ''),
            show_n=fill.get('show_n') if isinstance(fill.get('show_n'), int) else None,
            case_sensitive=bool(fill.get('case_sensitive')),
            grading_notes=str(fill.get('grading_notes') or ''),
        )
    return out


def problems_with(fill, kind):
    """Run the normal checks on what the AI proposed, so the teacher sees what's left to fix."""
    from .friendly import validate_values
    if kind != 'problem':
        return validate_values(fill['values'])
    options = {'markup': 'friendly', 'values': fill['values'], 'choices': fill['choices'], 'combos': fill['combos'],
               'show_n': fill['show_n'], 'case_sensitive': fill['case_sensitive'], 'shuffle': True}
    return get_qtype(fill['qtype']).validate(fill['question'], fill['answer'], options)
