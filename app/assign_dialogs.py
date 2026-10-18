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


def person_folders():
    """{person id: 'ids of every People folder they're in, or in one inside'} (a folder's Assign)."""
    people, _ = people_choices()
    return {u.id: f for u, f in people}
