"""Search Everything…: beside each folder page's filter box, ?search= looks in every folder, in names and what's inside,
and the page shows the matches as a folder view of its own, "Search: “fraction”", at the top of the folder list (the
owner, 2026-10-29, To do 76). The filter box stays: this folder, by name, as you type.

A page's route: `text()`; when there is some, `view = 'search'` and its list is `hits(every item, kind, text)`, paged as
usual; `entry(text, count, url)` goes in its folder list (folder_tree.kit's auto_views, or Student History's tree)."""
from flask import request

LONGEST = 100


def text():
    """The search typed, trimmed; '' when there's none."""
    return ' '.join((request.args.get('search') or '').split())[:LONGEST]


def _problem(p):
    return [p.title, p.raw_prob, p.teacher_note]


def _quiz(q):
    return [q.title, q.teacher_note] + [p.title for p in q.vproblems]


def _person(u):
    return [u.username, u.nickname, u.email, u.teacher_note]


def _named(x):
    return [getattr(x, 'name', None), getattr(x, 'teacher_note', None)]


def _attempt_kept(a):
    from app.qgen.trashnotes import of
    note = of('attempt', a.id)
    return [a.student_name, a.quiz_title, note.text if note else None]


def _attempt(cq):
    return [cq.vquiz.title if cq.vquiz else None, cq.taker.username if cq.taker else None,
            cq.taker.nickname if cq.taker else None]


def _waiting_quiz(q, attempts=()):
    #(Grading: a quiz waiting, with the names of its students who wait)
    return [q.title] + [n for cq in attempts if cq.taker for n in (cq.taker.username, cq.taker.nickname)]


def _group(g):
    #(My Quizzes, Student History: a quiz's group of attempts)
    q = g['vquiz']
    return [q.title] + [p.title for p in q.vproblems]


#what each kind looks in (the owner, 2026-10-29: names and what's inside, every teacher's Note too)
FIELDS = {'problems': _problem, 'quizzes': _quiz, 'people': _person, 'pictures': _named, 'files': _named,
          'workbooks': _named, 'attempts': _attempt_kept, 'pending': _attempt, 'grading': _waiting_quiz, 'groups': _group}


def hits(items, kind, words, extra=None):
    """The items with every word of the search in what they're searched by, case not minded; extra(item): more text
    for one (Grading's students)."""
    want = [w.lower() for w in words.split()]
    fields = FIELDS[kind]
    out = []
    for item in items:
        got = fields(item) + (list(extra(item)) if extra else [])
        hay = ' '.join(str(t) for t in got if t).lower()
        if all(w in hay for w in want):
            out.append(item)
    return out


def label(words):
    return 'Search: “{}”'.format(words)


def entry(words, count, url):
    """The folder list's entry for a search (folder_tree.kit's auto_views)."""
    return {'key': 'search', 'icon': 'search', 'label': label(words), 'count': count, 'badge': None, 'url': url,
            'tip': label(words)}


def nothing(words):
    return 'Nothing matches “{}”.'.format(words)


def apply(fk, words, count):
    """A page's folder kit (folder_tree.kit) switched to the search's own view: marked at the top of its folder list, the
    list's heading "Search: “x”" (named_box reads the entry's label), no folder open."""
    fk['view'], fk['node'], fk['path'] = 'search', None, []
    fk['auto_views'] = [entry(words, count, request.full_path.rstrip('?'))] + list(fk.get('auto_views') or ())
    fk['search_words'] = words
    fk['title'] = label(words)  # (the list's heading too, "Search: “x”")
    return fk
