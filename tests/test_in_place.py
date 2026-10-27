"""Actions done in place (the owner, 2026-10-27): with X-In-Place, a redirect back to the same page comes back as JSON
with its messages; a redirect to another page, or a message the page shows its own way, leaves the messages for that
page (the code critic, 2026-10-27)."""
from test_flow import app_db, login  # noqa: F401  (fixture)
from test_subjects import make_problems

PLACE = {'X-In-Place': '1'}


def test_same_page_gives_its_messages(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    probs = make_problems(teacher, 'Add')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Algebra'})
    g = VPGroup.query.filter_by(title='Algebra').one()
    res = teacher.post('/quiz/subjects/problems/file', data={'subject': g.id, 'items': [probs['Add'].id], 'action': 'add', 'view': 'all'},
                       headers=dict(PLACE, **{'X-In-Place-Page': '/quiz/listvp?folder=all'})).get_json()
    assert res['inplace'] and not res.get('navigate')
    assert res['messages'][-1] == {'html': 'Copied 1 problem to “Algebra”.', 'error': False}  # (after the setup's own, never shown)


def test_another_page_keeps_its_messages(app_db):
    app, db = app_db
    from app.qgen.models import VPGroup
    teacher = login(app, 'teach')
    teacher.post('/quiz/subjects/problems/new', data={'name': 'Gone soon'})
    g = VPGroup.query.filter_by(title='Gone soon').one()
    # deleting the folder being looked at: the page goes to All, the message waits for it there
    res = teacher.post('/quiz/subjects/problems/{}/delete'.format(g.id), data={'view': str(g.id)},
                       headers=dict(PLACE, **{'X-In-Place-Page': '/quiz/listvp?folder={}'.format(g.id)})).get_json()
    assert res['navigate'] and 'messages' not in res
    page = teacher.get(res['location']).data.decode()
    assert 'Deleted the folder' in page


def test_a_temporary_password_keeps_its_dialog(app_db):
    app, db = app_db
    from test_archive import ids
    teacher = login(app, 'teach')
    res = teacher.post('/resetpass/{}'.format(ids('sam')), headers=dict(PLACE, **{'X-In-Place-Page': '/userdet'})).get_json()
    assert res['navigate']
    page = teacher.get(res['location']).data.decode()
    assert 'Temporary password' in page
