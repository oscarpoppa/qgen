"""What every kind of folder on the site has in common (My quizzes, Users, the Problems and
Quizzes pages, the Archive): folders inside folders (at most MAX_DEPTH levels, never inside
themselves), names, and the tree a page draws with the folder list down the side.

A kind of folder is a small description (Kind below): its table, how a folder is named, and
which folders each thing is in. Some things are in one place only (an archived attempt, a
quiz on My quizzes); others can be in several (a person, a quiz on the Quizzes page).
Removing a folder never removes what's in it: it moves up a level."""
from app import db

MAX_NAME = 64
MAX_DEPTH = 6


class FolderError(ValueError):
    """Can't do it, worded for people."""


def clean_name(name):
    name = ' '.join((name or '').split())
    if not name:
        raise FolderError('Please give the folder a name.')
    if len(name) > MAX_NAME:
        raise FolderError('Please keep folder names under {} characters.'.format(MAX_NAME))
    return name


def depth(model, f):
    """1 for a folder at the top, 2 for one inside it..."""
    n = 0
    while f is not None:
        n += 1
        f = db.session.get(model, f.parent_id) if f.parent_id else None
    return n


def height(model, f, scope=None):
    """How many levels a folder is, with the folders inside it (1: none inside)."""
    q = model.query.filter_by(parent_id=f.id)
    if scope is not None:
        q = q.filter_by(**scope)
    return 1 + max((height(model, c, scope) for c in q.all()), default=0)


def check_new(model, parent):
    if parent is not None and depth(model, parent) >= MAX_DEPTH:
        raise FolderError('Folders can go only {} levels deep.'.format(MAX_DEPTH))


def check_move(model, f, target, scope=None):
    """May folder f go inside target (None: the top)? Raises FolderError if not."""
    up = target
    while up is not None:
        if up.id == f.id:
            raise FolderError('A folder can\'t go inside itself.')
        up = db.session.get(model, up.parent_id) if up.parent_id else None
    if target is not None and depth(model, target) + height(model, f, scope) > MAX_DEPTH:
        raise FolderError('Folders can go only {} levels deep.'.format(MAX_DEPTH))


def tree(folders, name, items, homes, key=lambda item: item.id):
    """The folders as a tree for a page: the top as {'folder': None, 'folders', 'items' (in
    no folder), 'count'}; each folder the same, with its own things in 'items', 'everyone'
    (the keys of everything in it or in the folders inside it) and 'count' (how many), and
    'depth'. Also returns every folder as (folder, depth) in list order (for "Move to"
    lists) and {folder id: node}.

    folders: the folder rows (each with .id and .parent_id), in the order to show them;
    name(folder) -> its name; items: the things, in the order to show them; homes: {key:
    [folder ids]} (no entry, or none that exist: in no folder)."""
    nodes = {f.id: {'folder': f, 'name': name(f), 'folders': [], 'items': [], 'ids': set()} for f in folders}
    root = {'folder': None, 'name': None, 'folders': [], 'items': [], 'ids': set(), 'depth': 0}
    for f in folders:
        (nodes[f.parent_id]['folders'] if f.parent_id in nodes else root['folders']).append(nodes[f.id])
    for item in items:
        places = [fid for fid in homes.get(key(item), ()) if fid in nodes]
        if not places:
            root['items'].append(item)
        for fid in places:
            nodes[fid]['items'].append(item)
            nodes[fid]['ids'].add(key(item))
    flat = []

    def walk(node, d):
        node['depth'] = d
        if node['folder'] is not None:
            flat.append((node['folder'], d))
        everyone = set(node['ids'])
        for child in node['folders']:
            everyone |= walk(child, d + 1)
        node['everyone'] = everyone
        node['count'] = len(everyone)
        return everyone
    walk(root, 0)
    root['count'] = len(root['items'])
    return root, flat, nodes


def inside(node):
    """The ids of a folder and every folder in it (it can't be moved into any of these)."""
    out = {node['folder'].id}
    for child in node['folders']:
        out |= inside(child)
    return out


def path(nodes, node):
    """The folders from the top down to node's folder."""
    out, up = [], node['folder'] if node else None
    while up is not None:
        out.insert(0, up)
        up = nodes[up.parent_id]['folder'] if up.parent_id in nodes else None
    return out


def view_of(choice, nodes, default='main', remember=True, extra=()):
    """What a page shows for ?folder=: 'main' (in no folder), 'all', or a folder's id (as
    text), with that folder's node (None for main and all). A folder that's gone: default.

    The choice is remembered for the page (by its endpoint, in the login session), so coming
    back to the page without ?folder= (from the menu, Home...) shows the same folder again."""
    from flask import has_request_context, request, session
    key = request.endpoint if remember and has_request_context() else None
    if choice is None and key:
        choice = (session.get('folder_views') or {}).get(key)
    choice = str(choice if choice is not None else default)
    if choice.isdigit() and int(choice) in nodes:
        view, node = choice, nodes[int(choice)]
    else:
        view, node = (choice if choice in ('main', 'all') + tuple(extra) else default), None
    if key:
        views = dict(session.get('folder_views') or {})
        if views.get(key) != view:
            views[key] = view
            session['folder_views'] = views
    return view, node


def indent(depth):
    """The spaces before a folder's name in a pick list, by how deep it is."""
    return '   ' * max(depth - 1, 0)


def kit(view, node, root, flat, nodes, page, **words):
    """What _folders.html needs to draw a page's folders. page(view) -> the page's address
    for 'main', 'all' or a folder's id. words: create_url, rename_url(id), delete_url(id),
    move_url, add_url / remove_url (things in several folders), unit / units ("quiz" /
    "quizzes"), all_label, placeholder, hint, drag_what, add_words, fold_key,
    all_count, name(folder), folder_icon(folder). The folder list's order is the same on
    every page: All, the automatic ones (auto_views), the folders, then Not in a folder."""
    out = {
        'view': view, 'node': node, 'root': root, 'flat': flat, 'nodes': nodes, 'page': page,
        'path': path(nodes, node), 'inside': inside, 'indent': indent,
        'max_name': MAX_NAME, 'max_depth': MAX_DEPTH,
        'main_label': 'Not in a folder',
        'name': lambda f: getattr(f, 'name', None) or getattr(f, 'title', ''),
        'folder_icon': lambda f: '📁', 'add_url': None, 'remove_url': None, 'box_tools': None, 'readonly': False,
        'add_words': 'Move to…', 'placeholder': 'Folder name',
        'title': None,  # a heading of its own instead of "All …" (My quizzes from a Home counter)
        #automatic entries in the side list after Not in a folder (My quizzes: New, In progress):
        #[{'key', 'icon', 'label', 'count', 'badge' (text for a badge while count, or None: a plain count)}]
        'auto_views': (),
        'purge_url': None,  # (folder id) -> where "Delete folder and everything in it" goes
        'purge_question': None,  # (node) -> its warning
        'purge_blocked': None,  # (node) -> why it can't be done yet (None: it can)
    }
    out['main_count'] = root['count']
    out.update(words)
    return out
