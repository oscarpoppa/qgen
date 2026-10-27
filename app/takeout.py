"""Taking things out of a folder, the same on every folder page (Problems, Quizzes, People).

The owner's rule (October 13, 2026): "Take out" takes something out of the folder and out of
the folders inside it, so it no longer shows in that folder, and says which folders it's still
in. Something that would then be in no folder at all is never changed without asking: "Do you
want me to permanently delete this or put it in Uncategorized?" (confirm='delete' or
'uncategorized'). Deleting is done the way that page deletes: an account is deleted (its quiz
attempts go to the Archive), a problem is deleted (one a quiz uses or students answered is kept
for those and quietly taken off the Problems page), a quiz is deleted (one students took goes to
Removed quizzes).
"""
from app import db

KINDS = ('problems', 'quizzes', 'people', 'archive', 'pictures', 'files')


class TakeOutError(ValueError):
    """Worded for people."""


def _folder_cls(kind):
    if kind == 'archive':
        from app.qgen.models import ArchiveFolder
        return ArchiveFolder
    if kind == 'people':
        from app.user.models import UserFolder
        return UserFolder
    from app.qgen import services as S
    return S.subject_kind(kind)[0]


def folder_name(kind, f):
    """A folder as every message here names it: its full path, outermost first (“8th Grade › abc”), as its chips show it,
    so two folders of one name are told apart (the owner, 2026-10-26)."""
    own = (lambda g: g.name) if kind == 'people' else (lambda g: g.title)
    names, seen, g = [own(f)], set(), f
    while getattr(g, 'parent_id', None) and g.parent_id not in seen:
        seen.add(g.parent_id)
        g = db.session.get(type(g), g.parent_id)
        if g is None:
            break
        names.append(own(g))
    return ' \u203a '.join(reversed(names))


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
    if kind == 'archive':
        from app.qgen.models import ArchivedAttempt as cls
    elif kind == 'people':
        from app.user.models import User
        cls = User
    else:
        from app.qgen import services as S
        cls = S.subject_kind(kind)[1]
    try:
        #(archived people too: the Archive's People has the same folder actions)
        item = db.session.get(cls, int(item_id), execution_options={'include_archived': True})
    except (TypeError, ValueError):
        item = None
    if item is None:
        raise TakeOutError('That {} doesn\'t exist any more.'.format({'problems': 'problem', 'quizzes': 'quiz', 'people': 'person', 'archive': 'attempt', 'pictures': 'picture', 'files': 'file'}[kind]))
    return item


def item_name(kind, item):
    if kind == 'archive':
        return '{}’s “{}”'.format(item.student_name, item.quiz_title)
    return item.shown_name if kind == 'people' else '“{}”'.format(item.title or 'Untitled')


def _folders_of(kind, item):
    """The ids of the folders the item is in."""
    if kind == 'archive':
        return {item.folder_id} if item.folder_id else set()
    if kind == 'people':
        from app.user.models import UserFolderMember
        return {m.folder_id for m in UserFolderMember.query.filter_by(user_id=item.id)}
    from app.qgen import services as S
    return {g.id for g in getattr(item, S.subject_kind(kind)[2])}


def _blocker(kind, item, by):
    """Why it can't be deleted, or None."""
    from app.qgen import services as S
    if kind == 'archive':
        return None
    if kind == 'people':
        return 'You can’t delete your own account.' if by is not None and item.id == by.id else None
    if kind in ('problems', 'pictures', 'files'):
        return None  # (one a quiz uses is kept, quietly off the Problems page: S.delete_problem)
    return S.vquiz_delete_blocker(item)


def plan(kind, item_ids, folder, by=None, one_folder=False, no_up=False):
    """What taking these out of the folder would do: {'out': items that stay in other folders,
    'up': items that go back up into the folder this one is inside (taken out of a folder inside
    another, a thing stays in that outer one, its Unsorted: the owner 2026-10-13, like deleting a
    folder), 'delete': items left in no folder (deleted if confirmed), 'blocked': [(item, why)]
    left in no folder but can't be deleted}. one_folder: just that folder (a folder chip's ✕),
    not the folders inside it. no_up: never up into the outer folder (the Move dialog's “Uncategorized”)."""
    ids = {folder.id} if one_folder else subtree(kind, folder)
    parent = db.session.get(_folder_cls(kind), folder.parent_id) if folder.parent_id and not no_up else None
    near = (subtree(kind, parent) - ids) if parent is not None else set()  # (the outer folder and its others)
    out, up, delete, blocked = [], [], [], []
    for item_id in dict.fromkeys(item_ids):
        item = _item(kind, item_id)
        mine = _folders_of(kind, item)
        if not mine & ids:
            continue  # not in it: nothing to do
        if parent is not None and not (mine - ids) & near:
            up.append(item)  # (back up into the outer folder; it keeps any others too)
            continue
        if mine - ids:
            out.append(item)
            continue
        #(the Move dialog's Uncategorized never deletes: no need to ask what would block it; the code critic, 2026-10-26)
        why = None if no_up else _blocker(kind, item, by)
        (blocked.append((item, why)) if why else delete.append(item))
    return {'out': out, 'up': up, 'delete': delete, 'blocked': blocked, 'ids': ids, 'parent': parent}


def question(kind, folder, p):
    """What to ask about the things that would be left in no folder (None if there are none)."""
    if not p['delete'] and not p['blocked']:
        return None
    left = p['delete'] + [i for i, _why in p['blocked']]
    one = len(left) == 1
    it = 'it' if one else 'them'
    if kind == 'people':
        it = 'him/her' if one else 'them'
    q = '{} {} only in “{}”. Do you want me to permanently delete {} or put {} in Uncategorized?'.format(
        ', '.join(item_name(kind, i) for i in left), 'is' if one else 'are', folder_name(kind, folder), it, it)
    if kind == 'people':
        q += ' Deleting an account sends its quiz attempts to the Trash.'
    elif kind == 'quizzes':
        q += ' A quiz students have taken goes to Removed quizzes instead, where you can restore it.'
    elif p['delete'] and kind == 'problems':
        #(the same warning as the problem's own Delete for good)
        from app.qgen import services as S
        archived = S.archived_counts()[1]
        for item in p['delete']:
            q += S.archive_warning(archived.get(item.id, 0), 'problem')
    for item, why in p['blocked']:
        q += ' {} can’t be deleted ({}), so {} would go in Uncategorized.'.format(
            item_name(kind, item), why.rstrip('.'), 'he/she' if kind == 'people' else 'it')
    return q


def preview(kind, folder, p):
    """Where each would go, said before it's done (the checked bar's Take out of folder: OK or
    Cancel, the owner 2026-10-15): up to the folder this one is in, else Uncategorized; nothing
    is deleted from there."""
    lines = []
    for item in p['up']:
        lines.append('{} will go to “{}”.'.format(item_name(kind, item), folder_name(kind, p['parent'])))
    for item in p['out']:
        lines.append('{} will stay in {}.'.format(item_name(kind, item), _still_in(kind, item, p['ids'])))
    for item in p['delete'] + [i for i, _why in p['blocked']]:
        lines.append('{} will go to Uncategorized (in no folder).'.format(item_name(kind, item)))
    return lines


def _still_in(kind, item, ids):
    """“A”, “B”: the folders it's in besides these."""
    rows = _folder_cls(kind).query.filter(_folder_cls(kind).id.in_(_folders_of(kind, item) - ids)).all()
    return ', '.join('“{}”'.format(folder_name(kind, f)) for f in sorted(rows, key=lambda f: folder_name(kind, f).lower()))


def _take_out(kind, item, ids):
    from app.qgen import services as S
    if kind == 'archive':
        if item.folder_id in ids:
            item.folder_id = None
        return
    if kind == 'people':
        from app.user.models import UserFolderMember
        UserFolderMember.query.filter(UserFolderMember.user_id == item.id,
                                      UserFolderMember.folder_id.in_(ids)).delete(synchronize_session=False)
    else:
        rel = getattr(item, S.subject_kind(kind)[2])
        for g in [g for g in rel if g.id in ids]:
            rel.remove(g)


def _put_in(kind, item, folder):
    from app.qgen import services as S
    if kind == 'archive':
        item.folder_id = folder.id
    elif kind == 'people':
        from app.user.models import UserFolderMember
        if db.session.get(UserFolderMember, (folder.id, item.id)) is None:
            db.session.add(UserFolderMember(folder_id=folder.id, user_id=item.id))
    else:
        rel = getattr(item, S.subject_kind(kind)[2])
        if folder not in rel:
            rel.append(folder)


def run(kind, item_ids, folder, by=None, confirm=None, one_folder=False, no_up=False):
    """Take them out. What would be left in no folder: confirm='delete' deletes it (what can't be
    deleted goes in Uncategorized), 'uncategorized' leaves it in no folder; anything else changes
    nothing (TakeOutError with the question). Returns the words for the message."""
    from app.qgen import services as S
    p = plan(kind, item_ids, folder, by, one_folder, no_up)
    if no_up:
        return _to_uncategorized(kind, p, folder)
    if (p['delete'] or p['blocked']) and confirm not in ('delete', 'uncategorized'):
        raise TakeOutError(question(kind, folder, p))
    ids, where = p['ids'], folder_name(kind, folder)
    done = []
    for item in p['up']:
        #(the folders it's in elsewhere, besides the outer one it goes back to: named too)
        also = _still_in(kind, item, ids | subtree(kind, p['parent']))
        _take_out(kind, item, ids)
        _put_in(kind, item, p['parent'])
        done.append('Took {} out of “{}”; {} now in “{}” (its Unsorted){}.'.format(item_name(kind, item), where,
                    'he/she is' if kind == 'people' else 'it’s', folder_name(kind, p['parent']),
                    ' and still in {}'.format(also) if also else ''))
    for item in p['out']:
        done.append('Took {} out of “{}”; {} still in {}.'.format(item_name(kind, item), where,
                    'he/she is' if kind == 'people' else 'it’s', _still_in(kind, item, ids)))
        _take_out(kind, item, ids)
    to_uncategorized = [i for i, _why in p['blocked']] + (p['delete'] if confirm == 'uncategorized' else [])
    for item in to_uncategorized:
        _take_out(kind, item, ids)
        done.append('Took {} out of “{}”; {} now in Uncategorized.'.format(item_name(kind, item), where,
                    'he/she is' if kind == 'people' else 'it’s'))
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
            elif kind == 'archive':
                S.purge_archived(item)  # (the Archive's own Delete for good)
                done.append('Deleted {} for good.'.format(name))
            elif kind in ('pictures', 'files'):
                #(an upload: the file itself, deleted for good; problems using a picture show none)
                from app.qgen import uploads
                uploads.delete_file(item)
                done.append('Deleted {} {} for good.'.format(S.item_word(kind), name))
            elif kind == 'problems':
                _take_out(kind, item, ids)
                how = S.delete_problem(item)
                done.append('Deleted problem {}.'.format(name) if how == 'deleted' else
                            'Deleted problem {} from Problems; the quizzes that use it keep it.'.format(name))
            else:
                #(out of the folder too, so restoring it doesn't put it back there)
                _take_out(kind, item, ids)
                how = S.delete_vquiz(item)
                done.append('Deleted quiz {}.'.format(name) if how == 'deleted' else
                            'Deleted quiz {} from Quizzes; students who took it keep it (restore it from Removed quizzes).'.format(name))
    return ' '.join(done) or 'Nothing to take out.'


def _to_uncategorized(kind, p, folder):
    """The Move dialog's “Uncategorized” (the owner, 2026-10-26, when Take out of folder went): out of the folder open
    now only. One that's in other folders too stays in them (a copy elsewhere is never lost); one in no other folder
    goes to Uncategorized. Nothing is deleted, nothing goes up into an outer folder."""
    ids, where, done = p['ids'], folder_name(kind, folder), []
    for item in p['out']:
        done.append('Moved {} out of “{}”; {} still in {}.'.format(item_name(kind, item), where,
                    'he/she is' if kind == 'people' else 'it’s', _still_in(kind, item, ids)))
        _take_out(kind, item, ids)
    for item in p['delete'] + [i for i, _why in p['blocked']]:
        _take_out(kind, item, ids)
        done.append('Moved {} to Uncategorized.'.format(item_name(kind, item)))
    db.session.commit()
    return ' '.join(done) or 'None of them is in “{}”.'.format(where)


def handle(kind, item_ids, folder_id, done, one_folder=False, no_up=False):
    """What every take-out route does. With check=1 nothing changes: JSON {ok, question} (the
    "are you sure?" when something would be deleted, else null), for static/js/takeout.js. A
    drag (fetch) that would delete something gets {ok: false, confirm: question} (409), and is
    sent again with confirm=1 once the person agrees. done(message, error=False): the reply."""
    from flask import request, jsonify
    from flask_login import current_user
    fetch = request.headers.get('X-Requested-With') == 'fetch'
    try:
        folder = get_folder(kind, folder_id)
        p = plan(kind, item_ids, folder, current_user, one_folder, no_up)
        q = None if no_up else question(kind, folder, p)
        can_delete = bool(p['delete'])  # (when nothing left can be deleted, "Delete for good" is grayed)
        if request.form.get('check'):
            return jsonify(ok=True, question=q, can_delete=can_delete, preview=preview(kind, folder, p))
        confirm = request.form.get('confirm')
        if q and confirm not in ('delete', 'uncategorized') and fetch:
            return jsonify(ok=False, confirm=q, can_delete=can_delete, preview=preview(kind, folder, p)), 409
        try:
            message = run(kind, item_ids, folder, by=current_user, confirm=confirm, one_folder=one_folder, no_up=no_up)
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


def _each_plan(kind, item_ids):
    """No folder open (All): each thing comes out of the folder it's in. In one folder: out of
    that one, up to the folder it's inside, else Uncategorized. In several: out of all of them,
    to Uncategorized. [(item, [its folders], where to)] (the owner, 2026-10-15)"""
    cls = _folder_cls(kind)
    out = []
    for item_id in dict.fromkeys(item_ids):
        item = _item(kind, item_id)
        if item is None:
            continue
        mine = _folders_of(kind, item)
        folders = sorted((db.session.get(cls, f) for f in mine), key=lambda f: folder_name(kind, f).lower())
        to = None
        if len(folders) == 1 and folders[0].parent_id:
            to = db.session.get(cls, folders[0].parent_id)
        out.append((item, folders, to))
    return out


def handle_each(kind, item_ids, done):
    """The checked bar's Take out of folder with no folder open: check=1 gives the preview."""
    from flask import request, jsonify
    plan_ = _each_plan(kind, item_ids)
    q = lambda fs: ' and '.join('“{}”'.format(folder_name(kind, f)) for f in fs)
    if request.form.get('check'):
        lines = []
        for item, folders, to in plan_:
            if not folders:
                lines.append('{} isn’t in any folder.'.format(item_name(kind, item)))
            else:
                lines.append('{} will come out of {} and go to {}.'.format(item_name(kind, item), q(folders),
                             '“{}”'.format(folder_name(kind, to)) if to else 'Uncategorized (in no folder)'))
        return jsonify(ok=True, question=None, can_delete=False, preview=lines)
    said = []
    for item, folders, to in plan_:
        if not folders:
            continue
        _take_out(kind, item, {f.id for f in folders})
        if to is not None:
            _put_in(kind, item, to)
        said.append('Took {} out of {}; {} now in {}.'.format(item_name(kind, item), q(folders),
                    'he/she is' if kind == 'people' else 'it’s',
                    '“{}”'.format(folder_name(kind, to)) if to else 'Uncategorized'))
    db.session.commit()
    return done(' '.join(said) or 'Nothing to take out: none of them is in a folder.')


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
        #(one in the Trash isn't counted: problems, quizzes, and pictures and files since 2026-10-26)
        items = [i for i in getattr(folder, S.subject_kind(kind)[3]) if not getattr(i, 'removed_at', None)]
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
                out.append('Still in {} other folders: {}.'.format('his/her' if kind == 'people' and len(rest) == 1 else 'their', names(rest)))
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
