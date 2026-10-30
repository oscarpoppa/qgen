"""The message written when something goes to the Trash or is deleted for good (the owner, 2026-10-29): sent in one notice
to every teacher, the one who did it too, and to the student when it's his/her attempt; kept with the item in the Trash
(TrashNote), where any teacher can change it. Informational only: nothing asks why.

Only problems, quizzes, people and students' attempts: pictures, other files and workbooks send nothing (the owner).
Nothing here commits: the caller does, with the change itself."""
from datetime import datetime

from flask import url_for

from app import db, tuning
from app.messages.models import notify, notify_teachers
from .models import TrashNote


def clean(text):
    """The message as typed, trimmed, at most the Technical setting's "Longest message"."""
    return (text or '').replace('\r', '').strip()[:tuning.get('max_message')]


def keep(kind, ids, text, by):
    """The message on each of these items in the Trash (replacing any earlier one); none when it's empty."""
    text = clean(text)
    ids = [i for i in ids if i is not None]
    drop(kind, ids)
    if not text:
        return
    for i in ids:
        db.session.add(TrashNote(kind=kind, item_id=i, text=text, by_id=by.id if by else None, at=datetime.now()))


def of(kind, item_id):
    return TrashNote.query.filter_by(kind=kind, item_id=item_id).first()


def by_item(kind, ids):
    """{item id: TrashNote} for a Trash list."""
    ids = list(ids)
    if not ids:
        return {}
    return {n.item_id: n for n in TrashNote.query.filter(TrashNote.kind == kind, TrashNote.item_id.in_(ids))}


def drop(kind, ids):
    """Gone with its item: deleted for good, or restored."""
    ids = [i for i in ids if i is not None]
    if ids:
        TrashNote.query.filter(TrashNote.kind == kind, TrashNote.item_id.in_(ids)).delete(synchronize_session=False)


def _said(text):
    text = clean(text)
    return ': “{}”'.format(text) if text else '.'


def tell(by, what, deleted=False, text='', names=None):
    """The teachers' notice: "dan moved the quiz “Food Quiz” to the Trash: “…”", "dan deleted … for good: “…”"; names: the
    students, for several attempts at once ("… to the Trash (ava, sam, kim): …")."""
    if by is None:
        return  # (a notice belongs to someone's record: nothing without who did it)
    who = by.username
    done = 'deleted {} for good'.format(what) if deleted else 'moved {} to the Trash'.format(what)
    shown = ' ({})'.format(', '.join(names[:6]) + (' and {} more'.format(len(names) - 6) if len(names) > 6 else '')) if names else ''
    body = '{} {}{}{}'.format(who, done, shown, _said(text))
    try:
        link = url_for('qgen.archive')
    except RuntimeError:
        link = None
    notify_teachers(by.id, body, link)


def tell_student(student_id, quiz_title, text=''):
    """The student's own notice, when his/her attempt is taken off My Quizzes: "Your teacher took away your attempt at
    “Food Quiz”: “…”" (no message: it ends after the quiz's name)."""
    text = clean(text)
    notify(student_id, 'Your teacher took away your attempt at “{}”{}'.format(quiz_title, ': “{}”'.format(text) if text else '.'))


#what the notices call each thing (the owner, 2026-10-29)
def problem(p):
    return 'the problem “{}”'.format(p.title or 'Untitled')


def quiz(q):
    return 'the quiz “{}”'.format(q.title or 'Untitled')


def person(u):
    return '{}’s account'.format(u.username)


def attempt(name, title):
    return '{}’s attempt at “{}”'.format(name, title)


def many(n, one, several):
    return '{} {}'.format(n, one if n == 1 else several)
