"""Folders on someone's own My quizzes page. Everyone (students and teachers) arranges
their own; nobody else sees them. A folder holds quizzes (each quiz with all its
attempts) and other folders. Removing a folder never deletes a quiz: what it held moves
up to where the folder was. Deleting a folder with everything in it sends its quizzes to
the Archive (a teacher can bring them back)."""
from app import db
from .models import QuizFolder, QuizPlacement, CQuiz



class FolderError(ValueError):
    """Can't do it, worded for people."""



def _max_name():
    """Longest folder name (Settings > Technical settings > Limits; the database column holds 64)."""
    from app import tuning
    return tuning.get('folder_name')


def _max_depth():
    """Folders inside folders, at most this many levels (a setting)."""
    from app import tuning
    return tuning.get('folder_depth')

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
    if len(name) > _max_name():
        raise FolderError('Please keep folder names under {} characters.'.format(_max_name()))
    return name


def _name_taken(user, name, parent_id, ignore=None):
    """Another of this student's folders at that level has the name (two folders side by side never share a
    name: the owner, 2026-10-26)."""
    low = name.lower()
    return any(f.name.lower() == low and f.id != ignore
               for f in QuizFolder.query.filter_by(owner_id=user.id, parent_id=parent_id))


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
    if parent is not None and _depth(parent) >= _max_depth():
        raise FolderError('Folders can go only {} levels deep.'.format(_max_depth()))
    name = _clean_name(name)
    if _name_taken(user, name, parent.id if parent else None):
        raise FolderError('There\u2019s already a folder called \u201c{}\u201d here.'.format(name))
    f = QuizFolder(owner_id=user.id, parent_id=parent.id if parent else None, name=name)
    db.session.add(f)
    db.session.commit()
    return f


def rename_folder(user, folder_id, name):
    f = _folder(user, folder_id)
    if f is None:
        raise FolderError('That folder isn\'t one of yours.')
    name = _clean_name(name)
    if _name_taken(user, name, f.parent_id, ignore=f.id):
        raise FolderError('There\u2019s already a folder called \u201c{}\u201d here.'.format(name))
    f.name = name
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


def _subtree(user, f):
    """A folder and every folder inside it, the deepest first."""
    out, todo = [], [f]
    while todo:
        g = todo.pop()
        out.append(g)
        todo.extend(QuizFolder.query.filter_by(owner_id=user.id, parent_id=g.id).all())
    return list(reversed(out))


def _quiz_ids_in(user, folder_ids):
    return {p.vquiz_id for p in QuizPlacement.query.filter(QuizPlacement.owner_id == user.id,
                                                          QuizPlacement.folder_id.in_(folder_ids))}


def not_handed_in(user, folder_id):
    """The quizzes in a folder (or the folders inside it) with a try not handed in yet
    (new or started), by title: such a folder can't be deleted with everything in it."""
    f = _folder(user, folder_id)
    if f is None:
        return []
    quiz_ids = _quiz_ids_in(user, {g.id for g in _subtree(user, f)})
    tries = CQuiz.query.filter(CQuiz.assignee == user.id, CQuiz.vquiz_id.in_(quiz_ids or [0]),
                               CQuiz.completed.is_(False), CQuiz.needs_review.is_(False)).all()
    return sorted({cq.vquiz.title for cq in tries})


def not_handed_in_note(titles):
    """Why a folder can't be deleted with everything in it yet (None: it can)."""
    if not titles:
        return None
    return 'First hand in every quiz in this folder. Still to do: {}.'.format(', '.join('“{}”'.format(t) for t in titles))


def delete_folder_and_quizzes(user, folder_id):
    """Delete a folder, the folders inside it and every quiz in them, once every one has been
    handed in (FolderError otherwise): each try at those quizzes goes to the Archive (as if a teacher took it away; it can be put back);
    nobody is told (the owner, 2026-10-29). Returns (folder name, how many quizzes)."""
    from .services import archive_attempt
    f = _folder(user, folder_id)
    if f is None:
        raise FolderError('That folder isn\'t one of yours.')
    #never a quiz still to do (new or started): only what's been handed in
    note = not_handed_in_note(not_handed_in(user, folder_id))
    if note:
        raise FolderError(note)
    tree = _subtree(user, f)
    ids = {g.id for g in tree}
    quiz_ids = _quiz_ids_in(user, ids)
    tries = CQuiz.query.filter(CQuiz.assignee == user.id, CQuiz.vquiz_id.in_(quiz_ids or [0])).all()
    titles = sorted({cq.vquiz.title for cq in tries})
    for cq in tries:
        archive_attempt(cq, by=user, reason='student folder')  # (16 characters at most)
    QuizPlacement.query.filter(QuizPlacement.owner_id == user.id, QuizPlacement.folder_id.in_(ids)) \
        .delete(synchronize_session=False)
    name = f.name
    for g in tree:
        db.session.delete(g)
    #(no notice to anyone: the owner, 2026-10-29; the quizzes are in the Trash's Attempts, as before)
    db.session.commit()
    return name, len(titles)


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
        if _depth(target) + _height(user, f) > _max_depth():
            raise FolderError('Folders can go only {} levels deep.'.format(_max_depth()))
    if (target.id if target else None) != f.parent_id and _name_taken(user, f.name, target.id if target else None, ignore=f.id):
        raise FolderError('There\u2019s already a folder called \u201c{}\u201d there. Rename one of them first.'.format(f.name))
    f.parent_id = target.id if target else None
    db.session.commit()
    return target


def tree(user, groups, due_ids=()):
    """My quizzes arranged in folders: the main list as {'folder': None, 'folders': [...],
    'groups': [...], 'count': quizzes inside, at any depth, and how many tries in them need
    the student: 'new' (not started), 'started' (started, not handed in) and 'due' (in
    due_ids: closing soon), each also as '<kind>_here' (not counting the folders inside)};
    each folder the same shape, with 'depth'. `groups` are attempts_by_quiz()'s, kept in
    their order. Also returns every folder as (folder, depth) in the order of a "Move to"
    list."""
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
        #(its count: only the quizzes loose in it, the owner 2026-10-25; 'total' has the folders inside too, for
        #"Delete the folder and everything in it")
        node['total'] = len(node['groups']) + sum(walk(child, depth + 1) for child in node['folders'])
        node['count'] = len(node['groups'])
        #tries that need the student, here and in the folders inside (the numbers on the folder,
        #and on every folder it's in): a quiz given twice and not started counts 2
        tests = {'new': lambda a: a.status == 'new',
                 'started': lambda a: a.status in ('started', 'review'),  # waiting for grading counts as in progress
                 'due': lambda a: a.id in due_ids}
        for kind, test in tests.items():
            node[kind + '_here'] = sum(1 for g in node['groups'] for a in g['attempts'] if test(a))
            node[kind] = node[kind + '_here'] + sum(child[kind] for child in node['folders'])
        return node['total']
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
