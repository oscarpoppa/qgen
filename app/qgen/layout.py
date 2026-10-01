"""A quiz's list of problems, stored as JSON in VQuiz.vpid_lst.

Each entry is either a problem id, or a group from which each student gets
a random few:

    [4, {"pick": 2, "from": [5, 6, 7, 8]}, 9]

Older quizzes are plain lists of ids and keep working unchanged.
"""
import json
import re


class LayoutError(ValueError):
    """A problem with the quiz's list, worded for the teacher."""


def parse(text):
    """Stored or submitted text -> list of entries. Accepts JSON or "4, 5, 7"."""
    text = (text or '').strip()
    if not text:
        return []
    if text.startswith('['):
        try:
            data = json.loads(text)
        except ValueError:
            raise LayoutError('The list of problems couldn\'t be read. Please tick them again.')
    else:
        data = [int(n) for n in re.findall(r'\d+', text)]
    out = []
    for entry in data:
        if isinstance(entry, dict):
            ids = [int(i) for i in entry.get('from') or []]
            out.append({'pick': int(entry.get('pick') or 1), 'from': ids})
        else:
            out.append(int(entry))
    return out


def dumps(layout):
    return json.dumps(layout)


def is_group(entry):
    return isinstance(entry, dict)


def all_ids(layout):
    """Every problem id mentioned, in order (a problem may appear more than once)."""
    ids = []
    for entry in layout:
        ids.extend(entry['from'] if is_group(entry) else [entry])
    return ids


def check(layout):
    """Plain-language errors about the groups themselves."""
    errors = []
    for n, entry in enumerate([e for e in layout if is_group(e)], 1):
        size = len(entry['from'])
        if size < 2:
            errors.append('Group {} has only one problem; a group needs at least two.'.format(n))
        elif not 1 <= entry['pick'] <= size:
            errors.append('Group {} has {} problems, so each student can get 1 to {} of them, not {}.'
                          .format(n, size, size, entry['pick']))
    return errors


def draw(layout, rng):
    """One student's problems, in quiz order, with each group's pick made."""
    ids = []
    for entry in layout:
        if is_group(entry):
            picked = set(rng.sample(range(len(entry['from'])), min(entry['pick'], len(entry['from']))))
            #keep the teacher's order within the group
            ids.extend(pid for i, pid in enumerate(entry['from']) if i in picked)
        else:
            ids.append(entry)
    return ids


def question_count(layout):
    return sum(min(e['pick'], len(e['from'])) if is_group(e) else 1 for e in layout)
