"""Taking things out of a folder, the same on every folder page (Problems, Quizzes, People).

The owner's rule (October 13, 2026): "Take out" takes something out of the folder and out of
the folders inside it, so it no longer shows in that folder, and says which folders it's still
in. Something that would then be in no folder at all is never changed without asking: "Do you
want me to permanently delete this or put it in Uncategorized?" (confirm='delete' or
'uncategorized'). Deleting is done the way that page deletes: an account is deleted (its quiz
attempts go to the Archive), a problem is deleted (refused, and left where it is, while a quiz
uses it or students answered it), a quiz is deleted (or, once assigned, goes to Removed quizzes).
"""
from app import db

KINDS = ('problems', 'quizzes', 'people')


class TakeOutError(ValueError):
    """Worded for people."""


def _folder_cls(kind):
    if kind == 'people':
        from app.user.models import UserFolder
        return UserFolder
    from app.qgen import services as S
    return S.subject_kind(kind)[0]


def folder_name(kind, f):
    return f.name if kind == 'people' else f.title


def get_folder(kind, folder_id):
    try:
        f = db.session.get(_folder_cls(kind), int(folder_id))
    except (TypeError, ValueError):
        f = None
    if f is None:
        raise TakeOutError('Pick a folder to take them out of.')
    return f


def subtree(kind, folder):
    """The folder's id and the ids of every folder inside it (at any depth)."""
    parent = dict(db.session.query(_folder_cls(kind).id, _folder_cls(kind).parent_id).all())
    out, grew = {folder.id}, True
    while grew:
        more = {fid for fid, p in parent.items() if p in out} - out
        grew = bool(more)
        out |= more
    return out


def _item(kind, item_id):
    if kind == 'people':
        from app.user.models import User
        cls = User
    else:
        from app.qgen import services as S
        cls = S.subject_kind(kind)[1]
    try:
        item = db.session.get(cls, int(item_id))
    except (TypeError, ValueError):
        item = None
    if item is None:
        raise TakeOutError('That {} doesn\'t exist any more.'.format({'problems': 'problem', 'quizzes': 'quiz', 'people': 'person'}[kind]))
    return item


def item_name(kind, item):
    return item.shown_name if kind == 'people' else '“{}”'.format(item.title or 'Untitled')


def _folders_of(kind, item):
    """The ids of the folders the item is in."""
    if kind == 'people':
        from app.user.models import UserFolderMember
        return {m.folder_id for m in UserFolderMember.query.filter_by(user_id=item.id)}
    from app.qgen import services as S
    return {g.id for g in getattr(item, S.subject_kind(kind)[2])}


def _blocker(kind, item, by):
    """Why it can't be deleted, or None."""
    from app.qgen import services as S
    if kind == 'people':
        return 'You can’t delete your own account.' if by is not None and item.id == by.id else None
    if kind == 'problems':
        return S.problem_delete_blocker(item)
    return S.vquiz_delete_blocker(item)


def plan(kind, item_ids, folder, by=None, one_folder=False):
    """What taking these out of the folder would do: {'out': items that stay in other folders,
    'delete': items left in no folder (deleted if confirmed), 'blocked': [(item, why)] left in
    no folder but can't be deleted}. one_folder: just that folder (a folder chip's ✕), not the
    folders inside it."""
    ids = {folder.id} if one_folder else subtree(kind, folder)
    out, delete, blocked = [], [], []
    for item_id in dict.fromkeys(item_ids):
        item = _item(kind, item_id)
        mine = _folders_of(kind, item)
        if not mine & ids:
            continue  # not in it: nothing to do
        if mine - ids:
            out.append(item)
            continue
        why = _blocker(kind, item, by)
        (blocked.append((item, why)) if why else delete.append(item))
    return {'out': out, 'delete': delete, 'blocked': blocked, 'ids': ids}


def question(kind, folder, p):
    """What to ask about the things that would be left in no folder (None if there are none)."""
    if not p['delete'] and not p['blocked']:
        return None
    left = p['delete'] + [i for i, _why in p['blocked']]
    one = len(left) == 1
    it = 'it' if one else 'them'
    if kind == 'people':
        it = 'them'
    q = '{} {} only in “{}”. Do you want me to permanently delete {} or put {} in Uncategorized?'.format(
        ', '.join(item_name(kind, i) for i in left), 'is' if one else 'are', folder_name(kind, folder), it, it)
    if kind == 'people':
        q += ' Deleting an account sends its quiz attempts to the Archive.'
    elif kind == 'quizzes':
        q += ' A deleted quiz goes to Removed quizzes, where you can restore it.'
    elif p['delete']:
        #(the same warning as the problem's own Delete)
        from app.qgen import services as S
        archived = S.archived_counts()[1]
        for item in p['delete']:
            q += S.archive_warning(archived.get(item.id, 0), 'problem')
    for item, why in p['blocked']:
        q += ' {} can’t be deleted ({}), so {} would go in Uncategorized.'.format(
            item_name(kind, item), why.rstrip('.'), 'they' if kind == 'people' else 'it')
    return q


def _still_in(kind, item, ids):
    """“A”, “B”: the folders it's in besides these."""
    rows = _folder_cls(kind).query.filter(_folder_cls(kind).id.in_(_folders_of(kind, item) - ids)).all()
    return ', '.join('“{}”'.format(folder_name(kind, f)) for f in sorted(rows, key=lambda f: folder_name(kind, f).lower()))


def _take_out(kind, item, ids):
    from app.qgen import services as S
    if kind == 'people':
        from app.user.models import UserFolderMember
        UserFolderMember.query.filter(UserFolderMember.user_id == item.id,
                                      UserFolderMember.folder_id.in_(ids)).delete(synchronize_session=False)
    else:
        rel = getattr(item, S.subject_kind(kind)[2])
        for g in [g for g in rel if g.id in ids]:
            rel.remove(g)


def run(kind, item_ids, folder, by=None, confirm=None, one_folder=False):
    """Take them out. What would be left in no folder: confirm='delete' deletes it (what can't be
    deleted goes in Uncategorized), 'uncategorized' leaves it in no folder; anything else changes
    nothing (TakeOutError with the question). Returns the words for the message."""
    from app.qgen import services as S
    p = plan(kind, item_ids, folder, by, one_folder)
    if (p['delete'] or p['blocked']) and confirm not in ('delete', 'uncategorized'):
        raise TakeOutError(question(kind, folder, p))
    ids, where = p['ids'], folder_name(kind, folder)
    done = []
    for item in p['out']:
        done.append('Took {} out of “{}”; {} still in {}.'.format(item_name(kind, item), where,
                    'they’re' if kind == 'people' else 'it’s', _still_in(kind, item, ids)))
        _take_out(kind, item, ids)
    to_uncategorized = [i for i, _why in p['blocked']] + (p['delete'] if confirm == 'uncategorized' else [])
    for item in to_uncategorized:
        _take_out(kind, item, ids)
        done.append('Took {} out of “{}”; {} now in Uncategorized.'.format(item_name(kind, item), where,
                    'they’re' if kind == 'people' else 'it’s'))
    db.session.commit()
    if confirm == 'delete':
        from flask import current_app
        for item in p['delete']:
            name = item_name(kind, item)
            current_app.logger.info('{} deleted {} {} (taken out of its only folder, “{}”)'.format(
                by.username if by is not None else '?', kind, name, where))
            if kind == 'people':
                from app.user.accounts import delete_account
                delete_account(item, by)
                done.append('Deleted {}’s account.'.format(name))
            elif kind == 'problems':
                S.delete_problem(item)
                done.append('Deleted problem {}.'.format(name))
            else:
                #(out of the folder too, so restoring it doesn't put it back there)
                _take_out(kind, item, ids)
                S.delete_vquiz(item)
                done.append('Deleted quiz {}: it’s in Removed quizzes, where you can restore it.'.format(name))
    return ' '.join(done) or 'Nothing to take out.'


def handle(kind, item_ids, folder_id, done, one_folder=False):
    """What every take-out route does. With check=1 nothing changes: JSON {ok, question} (the
    "are you sure?" when something would be deleted, else null), for static/js/takeout.js. A
    drag (fetch) that would delete something gets {ok: false, confirm: question} (409), and is
    sent again with confirm=1 once the person agrees. done(message, error=False): the reply."""
    from flask import request, jsonify
    from flask_login import current_user
    fetch = request.headers.get('X-Requested-With') == 'fetch'
    try:
        folder = get_folder(kind, folder_id)
        p = plan(kind, item_ids, folder, current_user, one_folder)
        q = question(kind, folder, p)
        can_delete = bool(p['delete'])  # (when nothing left can be deleted, "Delete for good" is grayed)
        if request.form.get('check'):
            return jsonify(ok=True, question=q, can_delete=can_delete)
        confirm = request.form.get('confirm')
        if q and confirm not in ('delete', 'uncategorized') and fetch:
            return jsonify(ok=False, confirm=q, can_delete=can_delete), 409
        try:
            message = run(kind, item_ids, folder, by=current_user, confirm=confirm, one_folder=one_folder)
        except Exception as exc:  # e.g. someone started the quiz meanwhile (S.ServiceError)
            from app import db as _db
            _db.session.rollback()
            if exc.__class__.__name__ not in ('ServiceError', 'GroupError'):
                raise
            return done(str(exc), error=True)
    except TakeOutError as exc:
        if request.form.get('check'):
            return jsonify(ok=False, error=str(exc)), 400
        return done(str(exc), error=True)
    return done(message)


def folder_delete_plan(kind, folder):
    """Before a folder is deleted (its contents move up a level): what will go where, for the
    message afterward. Returns a function that gives the message once it's done."""
    cls = _folder_cls(kind)
    parent = db.session.get(cls, folder.parent_id) if folder.parent_id else None
    inner = [folder_name(kind, f) for f in cls.query.filter_by(parent_id=folder.id).all()]
    if kind == 'people':
        from app.user.models import UserFolderMember, User
        ids = [m.user_id for m in UserFolderMember.query.filter_by(folder_id=folder.id)]
        items = User.query.filter(User.id.in_(ids)).all() if ids else []
    else:
        from app.qgen import services as S
        items = list(getattr(folder, S.subject_kind(kind)[3]))
    alone = [i for i in items if _folders_of(kind, i) == {folder.id}]  # in no other folder
    name = folder_name(kind, folder)
    names = lambda xs: ', '.join(item_name(kind, i) for i in sorted(xs, key=lambda i: item_name(kind, i).lower()))

    def message():
        out = ['Deleted the folder “{}”.'.format(name)]
        if parent is not None:
            if items:
                out.append('Moved to “{}” (its Unsorted): {}.'.format(folder_name(kind, parent), names(items)))
            if inner:
                out.append('Its folders {} are now inside “{}”.'.format(', '.join('“{}”'.format(n) for n in inner), folder_name(kind, parent)))
        else:
            if alone:
                out.append('Moved to Uncategorized: {}.'.format(names(alone)))
            rest = [i for i in items if i not in alone]
            if rest:
                out.append('Still in their other folders: {}.'.format(names(rest)))
            if inner:
                out.append('Its folders {} are now at the top level.'.format(', '.join('“{}”'.format(n) for n in inner)))
        if not items and not inner:
            out.append('It was empty.')
        return ' '.join(out)
    return message


def moved_up_message(name, parent, items, inner, top='Uncategorized'):
    """After deleting a folder whose things are each in one place (My quizzes, the Archive):
    what moved where. parent: the name of the folder they moved into (None: the top level,
    called `top`); items, inner: the names of the things and folders that were in it."""
    out = ['Deleted the folder “{}”.'.format(name)]
    if items:
        out.append('Moved to {}: {}.'.format('“{}” (its Unsorted)'.format(parent) if parent else top, ', '.join(items)))
    if inner:
        out.append('Its folders {} are now {}.'.format(', '.join('“{}”'.format(n) for n in inner),
                                                        'inside “{}”'.format(parent) if parent else 'at the top level'))
    if not items and not inner:
        out.append('It was empty.')
    return ' '.join(out)
