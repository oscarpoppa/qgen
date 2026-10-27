"""The Move dialog's “Uncategorized”, now that there's no Take out of folder (the owner, 2026-10-26): out of the folder
open now only. A copy in another folder stays, nothing goes up into an outer folder, nothing is deleted."""
from test_flow import app_db, login  # noqa: F401  (fixture)
from test_subjects import make_problems
from test_archive import ids
from test_user_folders import folder, in_folders, FETCH


def test_problems_out_of_the_open_folder_only(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup, VProblem
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add', 'Area')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Outer'})
    outer = VPGroup.query.filter_by(title='Outer').one()
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Inner', 'parent': outer.id})
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Top'})
    inner, top = VPGroup.query.filter_by(title='Inner').one(), VPGroup.query.filter_by(title='Top').one()
    for g in (inner, top):
        teacher.post('/quiz/subjects/problems/file', data={'subject': g.id, 'items': [probs['Add'].id], 'action': 'add'})
    teacher.post('/quiz/subjects/problems/file', data={'subject': inner.id, 'items': [probs['Area'].id], 'action': 'add'})
    r = teacher.post('/quiz/subjects/problems/file', follow_redirects=True, data={
        'subject': inner.id, 'items': [probs['Add'].id, probs['Area'].id], 'action': 'remove', 'to_none': '1', 'confirm': 'uncategorized'})
    page = r.data.decode().replace('&#8220;', '“').replace('&#8221;', '”').replace('&#8217;', '’')
    assert 'Moved “Add” out of “Outer › Inner”; it’s still in “Top”.' in page
    assert 'Moved “Area” to Uncategorized.' in page
    db.session.expire_all()
    titles = lambda t: sorted(g.title for g in VProblem.query.filter_by(title=t).one().vpgroups)
    assert titles('Add') == ['Top']  # (the copy kept; not up into Outer)
    assert titles('Area') == []  # (in no folder, not deleted, not up into Outer)
    assert VProblem.query.filter_by(title='Area').one().removed_at is None


def test_people_out_of_the_open_folder_only(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    teach.post('/users/folders', data={'name': '8th grade'})
    g8 = folder('8th grade')
    teach.post('/users/folders', data={'name': 'needs help', 'parent': g8})
    teach.post('/users/folders', data={'name': 'Math club'})
    special, club = folder('needs help'), folder('Math club')
    for who in ('sam', 'kim'):
        teach.post('/users/folders/add', data={'user': ids(who), 'to': special})
    teach.post('/users/folders/add', data={'user': ids('sam'), 'to': club})
    res = teach.post('/users/folders/file', headers=FETCH, data={
        'items': [ids('sam'), ids('kim')], 'folder': special, 'action': 'remove', 'to_none': '1', 'confirm': 'uncategorized'})
    assert res.get_json()['message'] == ('Moved sam out of “8th grade › needs help”; he/she is still in “Math club”. '
                                         'Moved kim to Uncategorized.')
    assert in_folders('sam') == ['Math club'] and in_folders('kim') == []
    from app.user.models import User
    assert User.query.filter_by(username='kim').count() == 1  # (never deleted)


def test_a_move_never_touches_the_other_copies(app_db):
    """A, B and C copies; moving C to another folder leaves A and B (the owner, 2026-10-27)."""
    app, db = app_db
    from app.qgen.models import VPGroup, VProblem
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add')
    for name in ('A', 'B', 'C', 'D', 'E'):
        teacher.post('/quiz/subjects/problems/new', data={'name': name})
    g = {n: VPGroup.query.filter_by(title=n).one().id for n in 'ABCDE'}
    teacher.post('/quiz/subjects/problems/file', data={'subject': [g['A'], g['B'], g['C']], 'items': [probs['Add'].id], 'action': 'add'})
    titles = lambda: (db.session.expire_all(), sorted(x.title for x in VProblem.query.filter_by(title='Add').one().vpgroups))[1]
    # from C's own page: out of C only
    teacher.post('/quiz/subjects/problems/file', data={'subject': g['D'], 'items': [probs['Add'].id], 'action': 'move', 'view': g['C']})
    assert titles() == ['A', 'B', 'D']
    # from All (which copy isn't known): put in E too, every copy kept, and said
    r = teacher.post('/quiz/subjects/problems/file', follow_redirects=True,
                     data={'subject': g['E'], 'items': [probs['Add'].id], 'action': 'move', 'view': 'all'})
    assert 'in several folders, so it was put there too and kept its others.' in r.data.decode().replace('&#8217;', '’')
    assert titles() == ['A', 'B', 'D', 'E']
    # one in a single folder, from All: out of that one
    probs2 = make_problems(teacher, 'Sub')
    teacher.post('/quiz/subjects/problems/file', data={'subject': g['A'], 'items': [probs2['Sub'].id], 'action': 'add'})
    teacher.post('/quiz/subjects/problems/file', data={'subject': g['B'], 'items': [probs2['Sub'].id], 'action': 'move', 'view': 'all'})
    db.session.expire_all()
    assert [x.title for x in VProblem.query.filter_by(title='Sub').one().vpgroups] == ['B']
