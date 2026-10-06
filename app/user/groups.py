"""Folders on the Users page (e.g. "7th grade"), shared by all the teachers. A person can be
in several folders, and folders can hold folders. A folder counts everyone in the folders
inside it too (assigning to "7th grade" includes "7th grade › Period 2"). Removing a folder
never removes anyone: its people and folders move up a level."""
from app import db
from .models import User, UserFolder, UserFolderMember

MAX_NAME = 64
MAX_DEPTH = 6


class GroupError(ValueError):
    """Can't do it, worded for people."""


def all_folders():
    return UserFolder.query.order_by(UserFolder.name, UserFolder.id).all()


def get(folder_id):
    """A folder by id (None for the main list); a missing one is refused."""
    if folder_id in (None, '', 'top', 'main', 0, '0'):
        return None
    try:
        f = db.session.get(UserFolder, int(folder_id))
    except (TypeError, ValueError):
        f = None
    if f is None:
        raise GroupError('That folder doesn\'t exist any more.')
    return f


def _person(user_id):
    try:
        u = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        u = None
    if u is None:
        raise GroupError('That person doesn\'t exist any more.')
    return u


def _clean_name(name):
    name = ' '.join((name or '').split())
    if not name:
        raise GroupError('Please give the folder a name.')
    if len(name) > MAX_NAME:
        raise GroupError('Please keep folder names under {} characters.'.format(MAX_NAME))
    return name


def _depth(f):
    n = 0
    while f is not None:
        n += 1
        f = db.session.get(UserFolder, f.parent_id) if f.parent_id else None
    return n


def _height(f):
    children = UserFolder.query.filter_by(parent_id=f.id).all()
    return 1 + max((_height(c) for c in children), default=0)


def create(name, parent_id=None):
    parent = get(parent_id)
    if parent is not None and _depth(parent) >= MAX_DEPTH:
        raise GroupError('Folders can go only {} levels deep.'.format(MAX_DEPTH))
    f = UserFolder(parent_id=parent.id if parent else None, name=_clean_name(name))
    db.session.add(f)
    db.session.commit()
    return f


def rename(folder_id, name):
    f = get(folder_id)
    if f is None:
        raise GroupError('That folder doesn\'t exist any more.')
    f.name = _clean_name(name)
    db.session.commit()
    return f


def remove(folder_id):
    """Remove a folder; its people and folders move up to where it was. Returns its name."""
    f = get(folder_id)
    if f is None:
        raise GroupError('That folder doesn\'t exist any more.')
    up = f.parent_id
    UserFolder.query.filter_by(parent_id=f.id).update({'parent_id': up}, synchronize_session=False)
    if up is not None:
        already = {m.user_id for m in UserFolderMember.query.filter_by(folder_id=up)}
        for m in UserFolderMember.query.filter_by(folder_id=f.id):
            if m.user_id not in already:
                db.session.add(UserFolderMember(folder_id=up, user_id=m.user_id))
    name = f.name
    db.session.delete(f)
    db.session.commit()
    return name


def move_folder(folder_id, to_id):
    """Put a folder inside another (or at the top level); never inside itself."""
    f = get(folder_id)
    if f is None:
        raise GroupError('That folder doesn\'t exist any more.')
    target = get(to_id)
    if target is not None:
        up = target
        while up is not None:
            if up.id == f.id:
                raise GroupError('A folder can\'t go inside itself.')
            up = db.session.get(UserFolder, up.parent_id) if up.parent_id else None
        if _depth(target) + _height(f) > MAX_DEPTH:
            raise GroupError('Folders can go only {} levels deep.'.format(MAX_DEPTH))
    f.parent_id = target.id if target else None
    db.session.commit()
    return target


def add(user_id, folder_id, moving_from=None):
    """Put someone in a folder (they stay in their other folders), or with moving_from, take
    them out of that one at the same time. Returns (person, folder)."""
    u, f = _person(user_id), get(folder_id)
    if f is None:
        raise GroupError('Pick a folder to put them in.')
    if db.session.get(UserFolderMember, (f.id, u.id)) is None:
        db.session.add(UserFolderMember(folder_id=f.id, user_id=u.id))
    if moving_from not in (None, '') and str(moving_from) != str(f.id):
        old = db.session.get(UserFolderMember, (get(moving_from).id, u.id))
        if old is not None:
            db.session.delete(old)
    db.session.commit()
    return u, f


def take_out(user_id, folder_id=None):
    """Take someone out of one folder, or (no folder) out of every folder: back to the main
    list. Returns (person, folder or None)."""
    u = _person(user_id)
    q = UserFolderMember.query.filter_by(user_id=u.id)
    f = get(folder_id)
    if f is not None:
        q = q.filter_by(folder_id=f.id)
    q.delete(synchronize_session=False)
    db.session.commit()
    return u, f


def tree(people):
    """The folders as a tree for the Users page: the main list as {'folder': None, 'folders',
    'people' (in no folder), 'count'}; each folder the same, with its own members in 'people'
    and 'count' = everyone in it or in folders inside it. Also every folder as (folder, depth)
    for the "Add to" lists, and {person id: [their folders]}."""
    folders = all_folders()
    by_user = {}
    members = {}
    for m in UserFolderMember.query.all():
        members.setdefault(m.folder_id, set()).add(m.user_id)
        by_user.setdefault(m.user_id, []).append(m.folder_id)
    nodes = {f.id: {'folder': f, 'folders': [], 'people': [], 'ids': members.get(f.id, set())} for f in folders}
    root = {'folder': None, 'folders': [], 'people': [], 'ids': set(), 'depth': 0}
    for f in folders:
        (nodes[f.parent_id]['folders'] if f.parent_id in nodes else root['folders']).append(nodes[f.id])
    for u in people:
        if u.id not in by_user:
            root['people'].append(u)
        for fid in by_user.get(u.id, []):
            if fid in nodes:
                nodes[fid]['people'].append(u)
    flat = []

    def walk(node, depth):
        node['depth'] = depth
        if node['folder'] is not None:
            flat.append((node['folder'], depth))
        everyone = set(node['ids'])
        for child in node['folders']:
            everyone |= walk(child, depth + 1)
        node['everyone'] = everyone
        node['count'] = len(everyone)
        return everyone
    walk(root, 0)
    root['count'] = len(root['people'])
    names = {f.id: f for f in folders}
    folders_of = {uid: sorted((names[fid] for fid in fids if fid in names), key=lambda f: f.name.lower())
                  for uid, fids in by_user.items()}
    return root, flat, nodes, folders_of


def inside(node):
    """The ids of a folder and every folder in it (it can't be moved into any of these)."""
    out = {node['folder'].id}
    for child in node['folders']:
        out |= inside(child)
    return out


def everyone_in(folder_id):
    """The ids of everyone in a folder or in the folders inside it."""
    f = get(folder_id)
    if f is None:
        return set()
    ids, todo = set(), [f.id]
    while todo:
        fid = todo.pop()
        ids |= {m.user_id for m in UserFolderMember.query.filter_by(folder_id=fid)}
        todo += [c.id for c in UserFolder.query.filter_by(parent_id=fid)]
    return ids


def picker():
    """For the Assign and Messages pages: every folder (indented by depth) with the ids of
    everyone in it, folders inside it included: [{'id', 'name', 'depth', 'path' ("7th grade ›
    Period 2"), 'ids'}]."""
    root, flat, nodes, _ = tree([])
    def path(f):
        names = [f.name]
        while f.parent_id in nodes:
            f = nodes[f.parent_id]['folder']
            names.insert(0, f.name)
        return ' › '.join(names)
    return [{'id': f.id, 'name': f.name, 'depth': depth, 'path': path(f), 'ids': sorted(nodes[f.id]['everyone'])} for f, depth in flat]


def state():
    """Changes whenever the folders or who's in them change (pages showing them refresh)."""
    folders = [(f.id, f.parent_id, f.name) for f in UserFolder.query.order_by(UserFolder.id)]
    members = sorted((m.folder_id, m.user_id) for m in UserFolderMember.query)
    return folders, members
