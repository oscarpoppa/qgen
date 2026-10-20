"""What the two Assign dialogs offer, for any page that includes them (the owner, 2026-10-15):
_dialog_assign_quizzes.html picks the people for given quizzes (static/js/assign_many.js), and
_dialog_assign_people.html picks the quizzes for given people (static/js/assign_people.js)."""


def people_choices():
    """[(person, 'ids of every People folder they're in, or in one inside')], [(folder, depth)]."""
    from app.user.models import User
    from app.user import groups
    people = User.query.order_by(User.username).all()
    _, flat, nodes, _ = groups.tree(people)
    return [(u, ' '.join(str(fid) for fid, n in nodes.items() if u.id in n['everyone'])) for u in people], flat


def quiz_choices():
    """[(quiz, 'ids of every Quizzes folder it's in, or in one inside')], [(folder, depth)]."""
    from app.qgen import services as S
    from app.qgen.models import VQuiz
    flat = S.subject_tree('quizzes')[1]
    parent = {g.id: g.parent_id for g, depth in flat}

    def up(fid):
        out = []
        while fid and fid not in out:
            out.append(fid)
            fid = parent.get(fid)
        return out
    return [(q, ' '.join(str(f) for g in q.vqgroups for f in up(g.id)))
            for q in S.in_use('quizzes').order_by(VQuiz.title).all()], flat


def assign_quizzes():
    """For the Assign dialog (people to quizzes): every quiz in use, A to Z, with the Quizzes
    page's folders as the folder list, like the people dialog (the owner, 2026-10-19)."""
    from app import folder_tree
    from app.qgen import services as S
    from app.qgen.models import VQuiz
    quizzes = S.in_use('quizzes').order_by(VQuiz.title).all()
    root = S.subject_tree('quizzes', items=quizzes)[0]
    return quizzes, folder_tree.filter_tree(root, lambda f: f.title, lambda fid: None, 'quiz:')


def pick_pictures():
    """For the problem editor's "Choose pictures" dialog (static/js/pickpictures.js; the owner,
    2026-10-19): every picture A to Z, with the Pictures page's folders as the folder list."""
    from app import folder_tree
    from app.qgen import services as S
    from app.qgen import uploads
    uploads.sync()
    root = S.subject_tree('pictures')[0]
    pictures = S.in_use('pictures').order_by(*S.upload_order('pictures')).all()
    return pictures, folder_tree.filter_tree(root, lambda f: f.title, lambda fid: None, 'pic:')


def person_folders():
    """{person id: 'ids of every People folder they're in, or in one inside'} (a folder's Assign)."""
    people, _ = people_choices()
    return {u.id: f for u, f in people}


def message_students():
    """For the Messages panel's "Write to…" box (the owner, 2026-10-17): every student, and
    People's folders as the same folder list and tabs as the Assign page's Students card."""
    from app import folder_tree
    from app.user.models import User
    from app.user import groups
    students = User.query.filter_by(is_admin=False).order_by(User.username).all()
    root, _, _, _ = groups.tree(students, only={u.id for u in students})
    return students, folder_tree.filter_tree(root, lambda f: f.name, lambda fid: None, 'user:')


def assign_people():
    """For the Assign dialog (quizzes to people): everyone not archived, with People's folders as
    the folder list and tabs, like the Messages panel's "Write to…" (the owner, 2026-10-18)."""
    from app import folder_tree
    from app.user.models import User
    from app.user import groups
    people = User.query.filter(User.archived_at.is_(None)).order_by(User.username).all()
    root, _, _, _ = groups.tree(people)
    return people, folder_tree.filter_tree(root, lambda f: f.name, lambda fid: None, 'user:')
