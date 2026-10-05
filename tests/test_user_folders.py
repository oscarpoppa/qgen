"""Folders on the Users page (e.g. "7th grade"): shared by the teachers, someone can be in
several, folders hold folders; usable on the Assign and Messages pages, which follow changes."""
import re

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_archive import ids

FETCH = {'X-Requested-With': 'fetch'}


def folder(name):
    from app.user.models import UserFolder
    return UserFolder.query.filter_by(name=name).one().id


def people(c, view=None):
    """The names in the Users page's tables (each table row once per listing)."""
    page = c.get('/userdet' + ('?folder={}'.format(view) if view is not None else '')).data.decode()
    return re.findall(r'data-name="([^"]+)"\s+title="Drag onto a folder', page)


def in_folders(name):
    from app.user.models import UserFolderMember, UserFolder
    return sorted(UserFolder.query.get(m.folder_id).name for m in UserFolderMember.query.filter_by(user_id=ids(name)))


def watch(c, key):
    return c.get('/messages/poll?watch=' + key).get_json()['watch']


def test_make_folders_and_put_people_in_them(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    r = teach.post('/users/folders', data={'name': ' 7th  grade '})
    g7 = folder('7th grade')
    assert r.headers['Location'].endswith('/userdet?folder={}'.format(g7))  # the new folder opens
    teach.post('/users/folders', data={'name': '8th grade'})
    teach.post('/users/folders', data={'name': 'Math club'})
    g8, club = folder('8th grade'), folder('Math club')
    assert sorted(people(teach)) == ['kim', 'sam', 'teach']  # the main list: nobody's in a folder yet
    # dragging from the main list puts them in; the "Add to folder" list too; several folders
    assert teach.post('/users/folders/move', data={'user': ids('sam'), 'to': g7, 'from': 'top'}, headers=FETCH).get_json() == \
        {'ok': True, 'message': 'Put sam in "7th grade".'}
    assert teach.post('/users/folders/add', data={'user': ids('sam'), 'to': club}, headers=FETCH).get_json()['message'] == \
        'Put sam in "Math club".'
    assert in_folders('sam') == ['7th grade', 'Math club']
    assert sorted(people(teach)) == ['kim', 'teach'] and people(teach, g7) == ['sam'] and people(teach, club) == ['sam']
    assert sorted(people(teach, 'all')) == ['kim', 'sam', 'teach']
    page = teach.get('/userdet?folder=all').data.decode()
    assert page.count('📁 7th grade</a>') == 1 and 'aria-label="Take sam out of Math club"' in page
    # dragging from one folder to another moves them (their other folders stay)
    assert teach.post('/users/folders/move', data={'user': ids('sam'), 'to': g8, 'from': g7}, headers=FETCH).get_json()['message'] == \
        'Moved sam to "8th grade".'
    assert in_folders('sam') == ['8th grade', 'Math club']
    # onto the main list from a folder: out of that folder; from All users: out of every folder
    teach.post('/users/folders/move', data={'user': ids('sam'), 'to': 'top', 'from': club})
    assert in_folders('sam') == ['8th grade']
    teach.post('/users/folders/add', data={'user': ids('sam'), 'to': club})
    assert teach.post('/users/folders/move', data={'user': ids('sam'), 'to': 'top', 'from': 'all'}, headers=FETCH).get_json()['message'] == \
        'Took sam out of every folder.'
    assert in_folders('sam') == []
    # the ✕ beside a folder
    teach.post('/users/folders/add', data={'user': ids('kim'), 'to': g7})
    assert teach.post('/users/folders/remove', data={'user': ids('kim'), 'folder': g7}, headers=FETCH).get_json()['message'] == \
        'Took kim out of "7th grade".'
    # names; renaming
    assert teach.post('/users/folders', data={'name': ' '}, headers=FETCH).get_json()['error'] == 'Please give the folder a name.'
    assert teach.post('/users/folders/{}/rename'.format(g7), data={'name': 'Grade 7'}, headers=FETCH).get_json()['ok']
    assert '<span class="side-name">Grade 7</span>' in teach.get('/userdet').data.decode()
    # teachers only: students never see or change them
    assert sam.get('/userdet').status_code == 302
    assert sam.post('/users/folders', data={'name': 'mine'}).status_code == 302
    assert sam.post('/users/folders/add', data={'user': ids('sam'), 'to': g8}).status_code == 302
    assert in_folders('sam') == [] and 'Grade 7' not in sam.get('/mypage').data.decode()
    # shared: another teacher sees the same folders
    from app.user.models import User
    t2 = User(username='t2', is_admin=True)
    t2.set_password('pw-for-tests')
    db.session.add(t2)
    db.session.commit()
    assert '<span class="side-name">Grade 7</span>' in login(app, 't2').get('/userdet').data.decode()


def test_folders_inside_folders_and_removing_them(app_db):
    app, db = app_db
    from app.user.models import UserFolder
    teach = login(app, 'teach')
    teach.post('/users/folders', data={'name': '7th grade'})
    g7 = folder('7th grade')
    teach.post('/users/folders', data={'name': 'Period 2', 'parent': g7})
    p2 = folder('Period 2')
    teach.post('/users/folders/add', data={'user': ids('sam'), 'to': p2})
    teach.post('/users/folders/add', data={'user': ids('kim'), 'to': g7})
    page = teach.get('/userdet?folder={}'.format(g7)).data.decode()
    # 7th grade: kim directly, and Period 2 as a box holding sam; it counts both
    assert people(teach, g7) == ['sam', 'kim'] and '<details class="sub-box" data-sub="{}">'.format(p2) in page
    assert re.search(r'7th grade</span></a>\s*<span class="side-count muted small"[^>]*>2<', page)
    assert 'aria-label="Expand all in 7th grade"' in page
    # not inside itself
    assert teach.post('/users/folders/move', data={'folder': g7, 'to': p2}, headers=FETCH).get_json()['error'] == \
        'A folder can\'t go inside itself.'
    # removing 7th grade: Period 2 and kim move up a level; nobody is deleted
    r = teach.post('/users/folders/{}/delete'.format(g7), data={'view': str(g7)}, headers=FETCH)
    assert r.get_json()['ok'] and db.session.get(UserFolder, p2).parent_id is None
    assert in_folders('kim') == [] and in_folders('sam') == ['Period 2']
    # removing Period 2 (inside nothing): sam back on the main list
    teach.post('/users/folders/{}/delete'.format(p2), data={})
    assert 'sam' in people(teach)
    # deleting an account takes it out of its folders
    teach.post('/users/folders', data={'name': 'G'})
    teach.post('/users/folders/add', data={'user': ids('kim'), 'to': folder('G')})
    from app.user.models import User, UserFolderMember
    db.session.delete(db.session.get(User, ids('kim')))
    db.session.commit()
    assert UserFolderMember.query.count() == 0


def test_assigning_and_messaging_a_folder(app_db):
    app, db = app_db
    from app.messages.models import Message
    teach = login(app, 'teach')
    teach.post('/users/folders', data={'name': '7th grade'})
    g7 = folder('7th grade')
    teach.post('/users/folders', data={'name': 'Period 2', 'parent': g7})
    p2 = folder('Period 2')
    teach.post('/users/folders/add', data={'user': ids('sam'), 'to': p2})
    teach.post('/users/folders/add', data={'user': ids('teach'), 'to': g7})  # a teacher in it gets no student message
    # Assign: a button per folder that checks everyone in it (folders inside included)
    page = teach.get('/quiz/assign').data.decode()
    assert 'data-ids="[{}, {}]">📁 7th grade'.format(*sorted([ids('sam'), ids('teach')])) in page
    # Messages: the folders down the side, a folder's students only
    page = teach.get('/messages').data.decode()
    assert '<span class="side-name">7th grade</span>' in page
    assert '<option value="folder:{}">📁 7th grade (1 student)</option>'.format(g7) in page
    rows = lambda v: re.findall(r'<td data-label="Student"><span class="person">.*?<strong>([^<]+)</strong>',
                                teach.get('/messages?folder={}'.format(v)).data.decode(), re.S)
    assert rows(g7) == ['sam'] and rows('main') == ['kim'] and sorted(rows('all')) == ['kim', 'sam']
    # writing to a folder reaches its students (folders inside included)
    teach.post('/messages/send', data={'to': 'folder:{}'.format(g7), 'body': 'Field trip Friday'})
    got = Message.query.filter_by(body='Field trip Friday').all()
    assert [m.student_id for m in got] == [ids('sam')]
    teach.post('/users/folders', data={'name': 'Empty'})
    r = teach.post('/messages/send', data={'to': 'folder:{}'.format(folder('Empty')), 'body': 'x'}, follow_redirects=True)
    assert 'Nobody in that folder is a student.' in r.data.decode()


def test_open_pages_follow_folder_changes(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    users, messages = watch(teach, 'users'), watch(teach, 'messages')
    teach.post('/users/folders', data={'name': '7th grade'})
    assert watch(teach, 'users') != users and watch(teach, 'messages') != messages
    users, messages = watch(teach, 'users'), watch(teach, 'messages')
    teach.post('/users/folders/add', data={'user': ids('sam'), 'to': folder('7th grade')})
    assert watch(teach, 'users') != users and watch(teach, 'messages') != messages
