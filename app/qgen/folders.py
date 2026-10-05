"""Folders on someone's own My quizzes page. Everyone (students and teachers) arranges
their own; nobody else sees them. A folder holds quizzes (each quiz with all its
attempts) and other folders. Deleting a folder never deletes a quiz: what it held moves
up to where the folder was."""
from app import db
from .models import QuizFolder, QuizPlacement, CQuiz

MAX_NAME = 64
MAX_DEPTH = 6  # folders inside folders, at most this many levels


class FolderError(ValueError):
    """Can't do it, worded for people."""


def folders_of(user):
    return QuizFolder.query.filter_by(owner_id=user.id).order_by(QuizFolder.name, QuizFolder.id).all()


def _folder(user, folder_id):
    """One of this person's folders (None for "the main list"); anyone else's is refused."""
    if folder_id in (None, '', 'top', 0, '0'):
        return None
    try:
        f = db.session.get(QuizFolder, int(folder_id))
    except (TypeError, ValueError):
        f = None
    if f is None or f.owner_id != user.id:
        raise FolderError('That folder isn\'t one of yours.')
    return f


def _clean_name(name):
    name = ' '.join((name or '').split())
    if not name:
        raise FolderError('Please give the folder a name.')
    if len(name) > MAX_NAME:
        raise FolderError('Please keep folder names under {} characters.'.format(MAX_NAME))
    return name


def _depth(f):
    """1 for a folder in the main list, 2 for one inside it..."""
    n = 0
    while f is not None:
        n += 1
        f = db.session.get(QuizFolder, f.parent_id) if f.parent_id else None
    return n


def _height(user, f):
    """How many levels this folder is, counting the folders inside it (1: none inside)."""
    children = QuizFolder.query.filter_by(owner_id=user.id, parent_id=f.id).all()
    return 1 + max((_height(user, c) for c in children), default=0)


def create_folder(user, name, parent_id=None):
    parent = _folder(user, parent_id)
    if parent is not None and _depth(parent) >= MAX_DEPTH:
        raise FolderError('Folders can go only {} levels deep.'.format(MAX_DEPTH))
    f = QuizFolder(owner_id=user.id, parent_id=parent.id if parent else None, name=_clean_name(name))
    db.session.add(f)
    db.session.commit()
    return f


def rename_folder(user, folder_id, name):
    f = _folder(user, folder_id)
    if f is None:
        raise FolderError('That folder isn\'t one of yours.')
    f.name = _clean_name(name)
    db.session.commit()
    return f


def delete_folder(user, folder_id):
    """Remove a folder; its quizzes and folders move up to where it was."""
    f = _folder(user, folder_id)
    if f is None:
        raise FolderError('That folder isn\'t one of yours.')
    up = f.parent_id
    QuizFolder.query.filter_by(owner_id=user.id, parent_id=f.id).update({'parent_id': up}, synchronize_session=False)
    if up is None:
        QuizPlacement.query.filter_by(owner_id=user.id, folder_id=f.id).delete(synchronize_session=False)
    else:
        QuizPlacement.query.filter_by(owner_id=user.id, folder_id=f.id).update({'folder_id': up}, synchronize_session=False)
    name = f.name
    db.session.delete(f)
    db.session.commit()
    return name


def move_quiz(user, vquiz_id, folder_id):
    """Put one of this person's quizzes (all its attempts) in a folder, or the main list."""
    try:
        vquiz_id = int(vquiz_id)
    except (TypeError, ValueError):
        raise FolderError('That quiz isn\'t on your list.')
    if not CQuiz.query.filter_by(assignee=user.id, vquiz_id=vquiz_id).first():
        raise FolderError('That quiz isn\'t on your list.')
    target = _folder(user, folder_id)
    row = db.session.get(QuizPlacement, (user.id, vquiz_id))
    if target is None:
        if row is not None:
            db.session.delete(row)
    elif row is None:
        db.session.add(QuizPlacement(owner_id=user.id, vquiz_id=vquiz_id, folder_id=target.id))
    else:
        row.folder_id = target.id
    db.session.commit()
    return target


def move_folder(user, folder_id, to_id):
    """Put a folder inside another (or in the main list); never inside itself."""
    f = _folder(user, folder_id)
    if f is None:
        raise FolderError('That folder isn\'t one of yours.')
    target = _folder(user, to_id)
    if target is not None:
        up = target
        while up is not None:
            if up.id == f.id:
                raise FolderError('A folder can\'t go inside itself.')
            up = db.session.get(QuizFolder, up.parent_id) if up.parent_id else None
        if _depth(target) + _height(user, f) > MAX_DEPTH:
            raise FolderError('Folders can go only {} levels deep.'.format(MAX_DEPTH))
    f.parent_id = target.id if target else None
    db.session.commit()
    return target


def tree(user, groups):
    """My quizzes arranged in folders: the main list as {'folder': None, 'folders': [...],
    'groups': [...], 'count': quizzes inside, at any depth}; each folder the same shape,
    with 'depth'. `groups` are attempts_by_quiz()'s, kept in their order. Also returns
    every folder as (folder, depth) in the order of a "Move to" list."""
    folders = folders_of(user)
    placed = {p.vquiz_id: p.folder_id for p in QuizPlacement.query.filter_by(owner_id=user.id)}
    nodes = {f.id: {'folder': f, 'folders': [], 'groups': [], 'count': 0} for f in folders}
    root = {'folder': None, 'folders': [], 'groups': [], 'count': 0, 'depth': 0}
    for f in folders:
        (nodes[f.parent_id]['folders'] if f.parent_id in nodes else root['folders']).append(nodes[f.id])
    for g in groups:
        (nodes[placed[g['vquiz'].id]] if placed.get(g['vquiz'].id) in nodes else root)['groups'].append(g)
    flat = []

    def walk(node, depth):
        node['depth'] = depth
        if node['folder'] is not None:
            flat.append((node['folder'], depth))
        node['count'] = len(node['groups']) + sum(walk(child, depth + 1) for child in node['folders'])
        return node['count']
    walk(root, 0)
    return root, flat


def index(root):
    """{folder id: its node} for every folder in the tree, and {quiz id: the folder it's in}."""
    nodes, home = {}, {}

    def walk(node):
        for g in node['groups']:
            home[g['vquiz'].id] = node['folder']
        for child in node['folders']:
            nodes[child['folder'].id] = child
            walk(child)
    walk(root)
    return nodes, home


def inside(node):
    """The ids of a folder and every folder in it (it can't be moved into any of these)."""
    out = {node['folder'].id}
    for child in node['folders']:
        out |= inside(child)
    return out
