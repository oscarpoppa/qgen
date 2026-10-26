"""Folders on the Users page (e.g. "7th grade"): shared by the teachers, someone can be in
several, folders hold folders; usable on the Assign and Messages pages, which follow changes."""
import re

from test_flow import app_db, login, no_titles, without_all_box, back_by_the_trail  # noqa: F401  (fixture)
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
        {'ok': True, 'message': 'Put sam in “7th grade”.'}
    assert teach.post('/users/folders/add', data={'user': ids('sam'), 'to': club}, headers=FETCH).get_json()['message'] == \
        'Put sam in “Math club”.'
    assert in_folders('sam') == ['7th grade', 'Math club']
    assert sorted(people(teach)) == ['kim', 'teach'] and people(teach, g7) == ['sam'] and people(teach, club) == ['sam']
    # All: one list, everyone once (sam is in both folders: two chips on one card)
    assert sorted(people(teach, 'all')) == ['kim', 'sam', 'teach']
    page = teach.get('/userdet?folder=all').data.decode()
    assert 'title="Open the folder “7th grade”">' in page and 'aria-label="Take sam out of Math club"' in page
    # dragging from one folder to another moves them (their other folders stay)
    assert teach.post('/users/folders/move', data={'user': ids('sam'), 'to': g8, 'from': g7}, headers=FETCH).get_json()['message'] == \
        'Moved sam to “8th grade”.'
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
    assert res.status_code == 409 and 'Do you want me to permanently delete him/her or put him/her in Uncategorized?' in res.get_json()['confirm']
    assert in_folders('sam') == ['8th grade']
    # the ✕ beside a folder
    # the ✕ beside a folder: the message says where they still are; out of their only folder,
    # asked first, then (as chosen) in Uncategorized
    teach.post('/users/folders/add', data={'user': ids('kim'), 'to': g7})
    teach.post('/users/folders/add', data={'user': ids('kim'), 'to': g8})
    assert teach.post('/users/folders/remove', data={'user': ids('kim'), 'folder': g7}, headers=FETCH).get_json()['message'] == \
        'Took kim out of “7th grade”; he/she is still in “8th grade”.'
    assert teach.post('/users/folders/remove', data={'user': ids('kim'), 'folder': g8}, headers=FETCH).status_code == 409
    assert teach.post('/users/folders/remove', data={'user': ids('kim'), 'folder': g8, 'confirm': 'uncategorized'},
                      headers=FETCH).get_json()['message'] == 'Took kim out of “8th grade”; he/she is now in Uncategorized.'
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
    # 7th grade: only kim, who's loose in it (sam is in Period 2), and it counts only kim (the owner, 2026-10-25)
    assert people(teach, g7) == ['kim'] and '"name": "Period 2"' in page  # (only its own: the owner, 2026-10-25)
    assert re.search(r'7th grade</span></a>\s*<span class="side-count muted small"[^>]*>1<', page)
    assert 'aria-label="Expand all in 7th grade"' in page
    # each person a row of the folder's table (People shown as rows)
    #(the page's own rows, each with its name for the filter; the dialogs' pickers list people as rows too)
    #(a row opens to the person's results too: one People page, the owner 2026-10-21)
    assert len(re.findall(r'<tr class="result-item" data-box="user:\d+" data-name=', page)) == 1  # kim only: sam is in Period 2 (the owner, 2026-10-25)
    assert '<tr class="result-item" data-box="user:{}" data-name="kim'.format(ids('kim')) in page
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
    # Messages (the panel's "Write to chosen students", the Messages page is retired): the
    # People folders down the side, students only (the teacher in 7th grade isn't there)
    page = teach.get('/dashboard').data.decode()
    page = page[page.index('id="write-to-dialog"'):page.index('</dialog>', page.index('id="write-to-dialog"'))]
    tree = json.loads(re.search(r'class="folder-filter-tree">(.*?)</script>', page, re.S).group(1))
    assert [(t['name'], [c['name'] for c in t['children']]) for t in tree] == [('7th grade', ['Period 2'])]
    # (a folder holds only who's loose in it, not who's in the folders inside it: the owner, 2026-10-25)
    assert tree[0]['keys'] == [] and tree[0]['children'][0]['keys'] == ['user:{}'.format(ids('sam'))]
    assert sorted(re.findall(r'name="students" value="(\d+)"', page)) == sorted([str(ids('kim')), str(ids('sam'))])
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
    #(the checked people go to the Assign page with them checked: the dialog became the page, the owner 2026-10-24)
    assert 'class="pick-person" name="users" value="{}"'.format(ids('kim')) in page
    assert 'id="assign-people-dialog"' not in page and 'js/assign_people.js' in page
    assert 'href="/quiz/assign?users={}"><svg'.format(ids('kim')) in no_titles(page) and 'aria-label="Assign quizzes"' in page  # (the paper plane: owner 2026-10-14)
    #(paper planes, the words for screen readers: owner 2026-10-14)
    #(no paper plane at the top for a folder: people are assigned from the Checked folder, the owner 2026-10-24)
    assert '/quiz/assign?folder=' not in page and 'Assign quizzes to this folder' not in page
    assert '/quiz/assign?folder=' not in teach.get('/userdet?folder={}'.format(p2)).data.decode()
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
    """People: one page with each person's results too (the owner, 2026-10-21; Accounts and Results
    were two views of it, 2026-10-09): no switch; Results by student's old address and the menu's
    People (whatever ?view= says) open it, keeping the folder; one student's page goes Back to People."""
    app, db = app_db
    teach = login(app, 'teach')
    from test_dashboard import make_quiz
    vq = make_quiz(app, teach, 'Week 1')
    accounts = no_titles(teach.get('/userdet?folder=all').data.decode())
    assert '<h1>People</h1>' in accounts and 'data-trail-key="people"' in accounts
    assert '>Accounts</a>' not in accounts and '>Results</a>' not in accounts and 'href="/quiz/listuser?folder=all"' not in accounts
    # its results are on it: the Quizzes, Status and Done columns, and the results' Show filter
    assert '<th data-sort-key="quizzes">Quizzes</th><th data-sort-key="average">Average</th><th data-sort-key="status">Status</th>' in accounts and 'id="results-filter"' in accounts
    assert teach.get('/people').headers['Location'] == '/userdet'
    assert teach.get('/quiz/listuser?folder=all').headers['Location'] == '/userdet?folder=all'
    #(the menu's People opens People, whatever ?view= asks: the owner, 2026-10-21)
    assert teach.get('/people?folder=all').headers['Location'] == '/userdet?folder=all'
    assert teach.get('/people?folder=all&view=results').headers['Location'] == '/userdet?folder=all'
    # the menu: one People entry, lit; no Results by student in the Quizzes menu (the owner, 2026-10-21),
    # no Results by quiz either (the owner, 2026-10-25)
    assert '>People</a>' in accounts and 'class="active" aria-current="page">People</a>' in accounts
    menu = accounts.split('<main')[0]
    assert '>Results by quiz</a>' not in menu and 'Results by student' not in menu
    # one student's page, a quiz's history and Results by quiz: the way back is the top bar's
    # arrows (the trail), no worded back button
    for url in ('/quiz/listuser/{}'.format(ids('sam')), '/quiz/results/{}'.format(vq.id)):
        assert back_by_the_trail(teach.get(url).data.decode()), url
    # one student's page: Assign a quiz to them
    #(it opens the Assign a quiz dialog: data-what names who it's for)
    assert 'href="/quiz/assign?users={}" data-what="sam">Assign quizzes to sam</a>'.format(ids('sam')) in \
        no_titles(teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode())


def test_users_page_leads_to_each_student_page(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    page = teach.get('/userdet?folder=all').data.decode()
    sam = ids('sam')
    #(the person icon: owner 2026-10-14)
    assert ('href="/quiz/listuser/{}" title="Student history: sam&#39;s quizzes, results and awards">'.format(sam) in page
            or 'href="/quiz/listuser/{}" title="Student history: sam\'s quizzes, results and awards">'.format(sam) in page) and 'aria-label="Student history"' in page
    # the name itself is plain text, not a link: only buttons act on a person
    assert '>sam</strong>' in page and 'class="box-title" title="Student · Last seen:' in page and 'class="person-link"' not in page
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
    # the bar: the same folder menu, Move to folder and Take out of folder as Problems and Quizzes;
    # each row: Take out of folder (it asks which folder when they're in several)
    assert 'id="file-form" class="file-bar" data-takeout="remove"' in page and '>Take out of folder</button>' in page and '>Move to folder</button>' in page
    assert page.count('aria-label="Take out of folder"') >= 2  # (icon buttons: their words for screen readers)
    res = teach.post('/users/folders/file', data={'items': [ids('sam'), ids('kim')], 'folder': g8, 'action': 'remove'}, headers=FETCH)
    assert res.status_code == 409 and res.get_json()['confirm'].startswith('kim is only in “8th grade”.')
    assert sorted(in_folders('sam')) == ['8th grade', 'Math club']  # nothing changed
    res = teach.post('/users/folders/file', data={'items': [ids('sam'), ids('kim')], 'folder': g8, 'action': 'remove', 'confirm': 'delete'}, headers=FETCH)
    assert res.get_json()['message'] == 'Took sam out of “8th grade”; he/she is still in “Math club”. Deleted kim’s account.'
    assert User.query.filter_by(username='kim').count() == 0 and in_folders('sam') == ['Math club']
    # never your own account: you go in Uncategorized instead
    teach.post('/users/folders/add', data={'user': ids('teach'), 'to': club})
    q = teach.post('/folders/people/takeout', data={'items': [ids('teach')], 'folder': club, 'check': '1'}, headers=FETCH).get_json()['question']
    assert 'can’t be deleted (You can’t delete your own account)' in q


def test_out_of_a_folder_inside_another_goes_back_up(app_db):
    """The owner's steps (2026-10-13): Ben in 8th grade, dragged into "needs special attention"
    inside it, then taken out of that: he's back in 8th grade (its Unsorted), not in no folder."""
    app, db = app_db
    teach = login(app, 'teach')
    teach.post('/users/folders', data={'name': '8th grade'})
    g8 = folder('8th grade')
    teach.post('/users/folders', data={'name': 'needs special attention', 'parent': g8})
    special = folder('needs special attention')
    teach.post('/users/folders/add', data={'user': ids('kim'), 'to': g8})
    teach.post('/users/folders/move', data={'user': ids('kim'), 'to': special, 'from': g8}, headers=FETCH)
    assert in_folders('kim') == ['needs special attention']
    # the ✕ on the folder, the card's Remove (just that folder), and the checked bar: all the same
    res = teach.post('/users/folders/remove', data={'user': ids('kim'), 'folder': special}, headers=FETCH).get_json()
    assert res['message'] == 'Took kim out of “needs special attention”; he/she is now in “8th grade” (its Unsorted).'
    assert in_folders('kim') == ['8th grade']
    teach.post('/users/folders/move', data={'user': ids('kim'), 'to': special, 'from': g8}, headers=FETCH)
    teach.post('/folders/people/takeout', data={'items': [ids('kim')], 'folder': special, 'just': '1', 'confirm': 'uncategorized'})
    assert in_folders('kim') == ['8th grade']
    # out of the top folder, with nothing else: still asked (delete or Uncategorized)
    assert teach.post('/users/folders/remove', data={'user': ids('kim'), 'folder': g8}, headers=FETCH).status_code == 409


def test_two_folders_side_by_side_never_share_a_name(app_db):
    """Two folders at the same level can't have the same name, on People and on My quizzes; moving one in beside a
    folder of its name is refused, asking for a rename (the owner, 2026-10-26)."""
    app, db = app_db
    import pytest
    from app.user import groups
    from app.user.models import User
    from app.qgen import folders as QF
    with app.app_context():
        g7 = groups.create('7th Grade')
        groups.create('Math', g7.id)
        top_math = groups.create('Math')          # (another level: fine)
        with pytest.raises(groups.GroupError, match='already a folder called “math” here'):
            groups.create('math', g7.id)
        other = groups.create('Science', g7.id)
        with pytest.raises(groups.GroupError, match='here'):
            groups.rename(other.id, 'MATH')
        with pytest.raises(groups.GroupError, match='already a folder called “Math” there. Rename one of them first.'):
            groups.move_folder(top_math.id, g7.id)
        groups.rename(top_math.id, 'Math 2')
        groups.move_folder(top_math.id, g7.id)
        sam = User.query.filter_by(username='sam').one()
        a = QF.create_folder(sam, 'math')
        QF.create_folder(sam, 'Inside', a.id)
        b = QF.create_folder(sam, 'Inside')
        with pytest.raises(QF.FolderError, match='already a folder called “Math” here'):
            QF.create_folder(sam, 'Math')
        with pytest.raises(QF.FolderError, match='there. Rename one of them first.'):
            QF.move_folder(sam, b.id, a.id)
        with pytest.raises(QF.FolderError, match='here'):
            QF.rename_folder(sam, b.id, 'MATH')
