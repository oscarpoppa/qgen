"""Folders on the Users page (e.g. "7th grade"): shared by the teachers, someone can be in
several, folders hold folders; usable on the Assign and Messages pages, which follow changes."""
import re

from test_flow import app_db, login, no_titles, without_all_box  # noqa: F401  (fixture)
from test_archive import ids

FETCH = {'X-Requested-With': 'fetch'}


def folder(name):
    from app.user.models import UserFolder
    return UserFolder.query.filter_by(name=name).one().id


def people(c, view='main'):
    """The names in the Users page's tables (each table row once per listing); the people in
    no folder to begin with (the page itself starts on everyone)."""
    page = without_all_box(c.get('/userdet' + ('?folder={}'.format(view) if view is not None else '')).data.decode())
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
    assert r.headers['Location'].endswith('/userdet?folder=main')  # you stay where you were
    r = teach.post('/users/folders', data={'name': 'Inside', 'parent': g7, 'view': str(g7)})
    assert r.headers['Location'].endswith('/userdet?folder={}'.format(g7))
    teach.post('/users/folders/{}/delete'.format(folder('Inside')), data={})
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
    # All: one list, everyone once (sam is in both folders: two chips on one card)
    assert sorted(people(teach, 'all')) == ['kim', 'sam', 'teach']
    page = teach.get('/userdet?folder=all').data.decode()
    assert 'title="Open the folder “7th grade”">' in page and 'aria-label="Take sam out of Math club"' in page
    # dragging from one folder to another moves them (their other folders stay)
    assert teach.post('/users/folders/move', data={'user': ids('sam'), 'to': g8, 'from': g7}, headers=FETCH).get_json()['message'] == \
        'Moved sam to "8th grade".'
    assert in_folders('sam') == ['8th grade', 'Math club']
    # onto the main list from a folder: out of that folder; from All users: out of every folder
    teach.post('/users/folders/move', data={'user': ids('sam'), 'to': 'top', 'from': club})
    assert in_folders('sam') == ['8th grade']
    teach.post('/users/folders/add', data={'user': ids('sam'), 'to': club})
    # from the All list onto Uncategorized: refused, as on the Problems and Quizzes pages (which
    # folder it came out of isn't known; the ✕ on a folder takes them out of that one)
    out = teach.post('/users/folders/move', data={'user': ids('sam'), 'to': 'top', 'from': 'all'}, headers=FETCH).get_json()
    assert 'Drag them out of a folder' in out['error']
    assert in_folders('sam') == ['8th grade', 'Math club']
    teach.post('/users/folders/move', data={'user': ids('sam'), 'to': 'top', 'from': club})
    # out of their only folder: that deletes their account, so it's asked first (not done here)
    res = teach.post('/users/folders/move', data={'user': ids('sam'), 'to': 'top', 'from': folder('8th grade')}, headers=FETCH)
    assert res.status_code == 409 and 'Do you want me to permanently delete them or put them in Uncategorized?' in res.get_json()['confirm']
    assert in_folders('sam') == ['8th grade']
    # the ✕ beside a folder
    # the ✕ beside a folder: the message says where they still are; out of their only folder,
    # asked first, then (as chosen) in Uncategorized
    teach.post('/users/folders/add', data={'user': ids('kim'), 'to': g7})
    teach.post('/users/folders/add', data={'user': ids('kim'), 'to': g8})
    assert teach.post('/users/folders/remove', data={'user': ids('kim'), 'folder': g7}, headers=FETCH).get_json()['message'] == \
        'Took kim out of “7th grade”; they’re still in “8th grade”.'
    assert teach.post('/users/folders/remove', data={'user': ids('kim'), 'folder': g8}, headers=FETCH).status_code == 409
    assert teach.post('/users/folders/remove', data={'user': ids('kim'), 'folder': g8, 'confirm': 'uncategorized'},
                      headers=FETCH).get_json()['message'] == 'Took kim out of “8th grade”; they’re now in Uncategorized.'
    assert in_folders('kim') == []
    # names; renaming
    assert teach.post('/users/folders', data={'name': ' '}, headers=FETCH).get_json()['error'] == 'Please give the folder a name.'
    assert teach.post('/users/folders/{}/rename'.format(g7), data={'name': 'Grade 7'}, headers=FETCH).get_json()['ok']
    assert '<span class="side-name">Grade 7</span>' in teach.get('/userdet').data.decode()
    # teachers only: students never see or change them
    assert sam.get('/userdet').status_code == 302
    assert sam.post('/users/folders', data={'name': 'mine'}).status_code == 302
    assert sam.post('/users/folders/add', data={'user': ids('sam'), 'to': g8}).status_code == 302
    assert in_folders('sam') == ['8th grade'] and 'Grade 7' not in sam.get('/mypage').data.decode()
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
    # 7th grade: one list of kim (directly) and sam (in Period 2), with a folder button for Period 2; it counts both
    assert people(teach, g7) == ['kim', 'sam'] and '"name": "Period 2"' in page
    assert re.search(r'7th grade</span></a>\s*<span class="side-count muted small"[^>]*>2<', page)
    assert 'aria-label="Expand all in 7th grade"' in page
    # each person a box that folds to their name (like My quizzes' quizzes), so Expand all /
    # Collapse all works inside a folder too
    assert page.count('<details class="box card person-card" data-list data-box="user:') == 2  # kim, and sam in Period 2's box
    assert '<details class="box card person-card" data-list data-box="user:{}"'.format(ids('kim')) in page
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
    # Assign: one checklist, each person once, with the People folders as tabs over it
    # (static/js/folderfilter.js): 7th grade holds Period 2, which holds sam
    import json
    page = teach.get('/quiz/assign').data.decode()
    page = page[page.index('id="pick-people"'):]  # (the Students card; the Quiz card is beside it)
    tree = json.loads(re.search(r'class="folder-filter-tree">(.*?)</script>', page, re.S).group(1))
    assert [(t['id'], [c['id'] for c in t['children']]) for t in tree] == [(g7, [p2])]
    assert tree[0]['children'][0]['keys'] == ['user:{}'.format(ids('sam'))]
    assert page.count('type="checkbox" name="users"') == 3 and page.count('data-user="{}"'.format(ids('sam'))) == 1
    assert 'data-all-label="All people"' in page and 'data-start="all"' in page
    # someone checked twice gets one copy
    from test_dashboard import make_quiz
    from app.qgen.models import CQuiz
    vq = make_quiz(app, teach, 'Twice')
    teach.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam'), ids('sam')]})
    assert CQuiz.query.filter_by(vquiz_id=vq.id, assignee=ids('sam')).count() == 1
    # Messages: the folders down the side, a folder's students only
    page = teach.get('/messages').data.decode()
    assert '<span class="side-name">7th grade</span>' in page
    assert '<option value="folder:{}">7th grade (1 student)</option>'.format(g7) in page
    rows = lambda v: re.findall(r'<td data-label="Student"><a class="name-link person"[^>]*>.*?<strong>([^<]+)</strong>',
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


def test_assigning_from_the_users_page(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    teach.post('/users/folders', data={'name': '7th grade'})
    g7 = folder('7th grade')
    teach.post('/users/folders', data={'name': 'Period 2', 'parent': g7})
    p2 = folder('Period 2')
    teach.post('/users/folders/add', data={'user': ids('sam'), 'to': p2})
    teach.post('/users/folders/add', data={'user': ids('kim'), 'to': g7})
    # each person: a box to check (for the bar) and a quick Assign; a folder: Assign a quiz to this folder
    page = teach.get('/userdet?folder={}'.format(g7)).data.decode()
    assert 'name="users" value="{}" form="assign-people"'.format(ids('kim')) in page
    assert '<form method="get" action="/quiz/assign" id="assign-people"' in page
    assert 'href="/quiz/assign?users={}">Assign a quiz</a>'.format(ids('kim')) in no_titles(page)
    assert 'href="/quiz/assign?folder={}">Assign a quiz to this folder</a>'.format(g7) in no_titles(page)
    assert 'href="/quiz/assign?folder={}">Assign a quiz<span class="wide-only"> to this folder</span></a>'.format(p2) in no_titles(page)  # the box inside
    checked = lambda page: sorted(int(i) for i in re.findall(r'name="users" value="(\d+)" id="users-\d+" data-user="\d+" data-name="[^"]*" checked', page))
    start = lambda page: re.search(r'data-start="(\w+)"', page[page.index('id="pick-people"'):]).group(1)
    # a folder: everyone in it (and in the folders inside it), checked, opening on its tab
    page = teach.get('/quiz/assign?folder={}'.format(g7)).data.decode()
    assert checked(page) == sorted([ids('sam'), ids('kim')]) and start(page) == str(g7)
    page = teach.get('/quiz/assign?folder={}'.format(p2)).data.decode()
    assert checked(page) == [ids('sam')] and start(page) == str(p2)
    # people by name (twice is once), on All people; nonsense ignored
    page = teach.get('/quiz/assign?users={0}&users={0}&users=x&users=99999'.format(ids('sam'))).data.decode()
    assert checked(page) == [ids('sam')] and start(page) == 'all'


def test_results_pages_lead_back_to_users(app_db):
    """People: Accounts and Results are two views of one page (2026-10-09): each has the
    switch, keeping the folder; the menu's People opens the view used last; one student's
    page goes Back to People."""
    app, db = app_db
    teach = login(app, 'teach')
    from test_dashboard import make_quiz
    vq = make_quiz(app, teach, 'Week 1')
    accounts = no_titles(teach.get('/userdet?folder=all').data.decode())
    assert '<h1>People</h1>' in accounts and 'data-trail-key="people"' in accounts
    assert 'href="/userdet?folder=all" aria-current="page">Accounts</a>' in accounts and 'href="/quiz/listuser?folder=all">Results</a>' in accounts
    assert teach.get('/people').headers['Location'] == '/userdet'
    results = no_titles(teach.get('/quiz/listuser?folder=all').data.decode())
    assert '<h1>People</h1>' in results and 'href="/quiz/listuser?folder=all" aria-current="page">Results</a>' in results
    assert teach.get('/people?folder=all').headers['Location'] == '/quiz/listuser?folder=all'  # used last
    # the menu: one People entry, lit on both views; Results by student isn't in the Quizzes menu
    assert '>People</a>' in results and 'class="active" aria-current="page">People</a>' in results
    assert '>Results by student</a>' not in results.split('<main')[0]
    assert '<a class="btn btn-secondary" href="/people" data-back><span class="back-label">← People</span></a>' in \
        no_titles(teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode())
    # one quiz's history is about the quiz: back to Quizzes (when there's no trail to follow)
    assert '<a class="btn btn-secondary" href="/quiz/listvq" data-back><span class="back-label">← Quizzes</span></a>' in \
        no_titles(teach.get('/quiz/results/{}'.format(vq.id)).data.decode())
    # results by quiz are about quizzes, not people: back to the Dashboard (when there's no trail)
    assert '<a class="btn btn-secondary" href="/dashboard" data-back><span class="back-label">← Dashboard</span></a>' in no_titles(teach.get('/quiz/results').data.decode())
    # one student's page: Assign a quiz to them
    assert 'href="/quiz/assign?users={}">Assign a quiz to sam</a>'.format(ids('sam')) in \
        no_titles(teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode())


def test_users_page_leads_to_each_student_page(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    page = teach.get('/userdet?folder=all').data.decode()
    sam = ids('sam')
    assert 'href="/quiz/listuser/{}" title="sam&#39;s quizzes, results and awards">Student page</a>'.format(sam) in page \
        or 'href="/quiz/listuser/{}" title="sam\'s quizzes, results and awards">Student page</a>'.format(sam) in page
    # the name itself is plain text, not a link: only buttons act on a person
    assert '<strong class="box-title">sam</strong>' in page and 'class="person-link"' not in page
    assert '>Quizzes</a>' not in page


def test_taking_people_out_of_their_only_folder(app_db):
    """People: a card's Take out and the checked bar's "Take out of folder" (the same route as
    Problems and Quizzes): where they're still in; out of their only folder, asked first, then
    their account deleted (attempts kept in the Archive) or they go in Uncategorized."""
    app, db = app_db
    from app.user.models import User
    teach = login(app, 'teach')
    for name in ('8th grade', 'Math club'):
        teach.post('/users/folders', data={'name': name})
    g8, club = folder('8th grade'), folder('Math club')
    for who in ('sam', 'kim'):
        teach.post('/users/folders/add', data={'user': ids(who), 'to': g8})
    teach.post('/users/folders/add', data={'user': ids('sam'), 'to': club})
    page = teach.get('/userdet?folder=all').data.decode()
    # the bar: the same folder menu, Put in folder and Take out of folder as Problems and Quizzes;
    # each card: Remove (it asks which folder when they're in several)
    assert 'id="file-form" class="file-bar" data-takeout="remove"' in page and '>Take out of folder</button>' in page and '>Put in folder</button>' in page
    assert page.count('>Remove</button>') >= 2
    res = teach.post('/users/folders/file', data={'items': [ids('sam'), ids('kim')], 'folder': g8, 'action': 'remove'}, headers=FETCH)
    assert res.status_code == 409 and res.get_json()['confirm'].startswith('kim is only in “8th grade”.')
    assert sorted(in_folders('sam')) == ['8th grade', 'Math club']  # nothing changed
    res = teach.post('/users/folders/file', data={'items': [ids('sam'), ids('kim')], 'folder': g8, 'action': 'remove', 'confirm': 'delete'}, headers=FETCH)
    assert res.get_json()['message'] == 'Took sam out of “8th grade”; they’re still in “Math club”. Deleted kim’s account.'
    assert User.query.filter_by(username='kim').count() == 0 and in_folders('sam') == ['Math club']
    # never your own account: you go in Uncategorized instead
    teach.post('/users/folders/add', data={'user': ids('teach'), 'to': club})
    q = teach.post('/folders/people/takeout', data={'items': [ids('teach')], 'folder': club, 'check': '1'}, headers=FETCH).get_json()['question']
    assert 'can’t be deleted (You can’t delete your own account)' in q
