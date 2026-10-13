"""The review pass: only this site's pages after signing in or an action, pages that keep
up (and stay quick), Back buttons that go where you came from, the grading queue, what a
student is offered after handing in, nicknames, and wording a young student understands."""
import re
from datetime import datetime, timedelta

from sqlalchemy import event

from test_flow import app_db, login, take_page, no_titles  # noqa: F401  (fixture)
from test_dashboard import make_quiz, give
from test_archive import ids
from app.icons import icon as ico


def poll(client, key):
    return client.get('/messages/poll?watch=' + key).get_json()['watch']


# ---------------------------------------------------------------- only this site

def test_login_only_follows_this_sites_pages(app_db):
    app, db = app_db
    for bad in ('https://evil.example/x', '//evil.example/x', 'javascript:alert(1)', '/\\evil.example', 'http://evil.example'):
        c = app.test_client()
        r = c.post('/login?next=' + bad, data={'username': 'sam', 'password': 'pw-for-tests'})
        assert r.status_code == 302 and r.headers['Location'] == '/home', bad
    c = app.test_client()
    r = c.post('/login?next=/profile', data={'username': 'sam', 'password': 'pw-for-tests'})
    assert r.headers['Location'] == '/profile'


def test_safe_next(app_db):
    app, db = app_db
    from app.nav import safe_next
    with app.test_request_context('/', base_url='http://localhost'):
        assert safe_next('/quiz/listvq?folder=2#x', 'F') == '/quiz/listvq?folder=2#x'
        assert safe_next('http://localhost/quiz/results', 'F') == '/quiz/results'
        for bad in (None, '', 'quiz', '//evil', 'https://evil/quiz', 'ftp://localhost/x', '/\\evil', 'javascript:x', '/a\nb'):
            assert safe_next(bad, 'F') == 'F', bad
        # the live site: nginx passes the name on without the port, the browser's address has it
        assert safe_next('http://localhost:8080/quiz/results?folder=2', 'F') == '/quiz/results?folder=2'
        assert safe_next('http://evil:8080/quiz', 'F') == 'F' and safe_next('http://localhost.evil/x', 'F') == 'F'
    # when the port is known, only that port is this site
    with app.test_request_context('/', base_url='http://localhost:5057'):
        assert safe_next('http://localhost:5057/quiz/results', 'F') == '/quiz/results'
        assert safe_next('http://localhost:8080/quiz/results', 'F') == 'F'


def test_actions_dont_go_back_to_another_site(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    cq = give(vq, 'sam')
    r = teach.post('/quiz/delcq/{}'.format(cq.id), headers={'Referer': 'https://evil.example/'})
    assert r.status_code == 302 and 'evil' not in r.headers['Location']


# ---------------------------------------------------------------- pages that keep up

def test_home_moves_on_with_time(app_db):
    app, db = app_db
    sam = login(app, 'sam')
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    give(vq, 'sam', closes_at=datetime.now() + timedelta(days=3))
    home = sam.get('/home').data.decode()
    drawn = re.search(r'data-watch="home" data-watch-state="(\w+)"', home).group(1)
    assert poll(sam, 'home') == drawn
    # two days later it is "due soon": the open Home notices
    from app import live
    from flask_login import login_user
    from app.user.models import User
    with app.test_request_context():
        login_user(db.session.get(User, ids('sam')))
        later = live.state('home', now=datetime.now() + timedelta(days=2))
        assert later != live.state('home')


def test_users_page_doesnt_reload_for_each_hour_ago(app_db):
    app, db = app_db
    from app import live
    from app.user.models import User
    from flask_login import login_user
    sam = db.session.get(User, ids('sam'))
    now = datetime.now().replace(hour=15, minute=0)
    sam.last_seen, sam.logged_in = now - timedelta(hours=2), False
    db.session.commit()
    with app.test_request_context():
        login_user(db.session.get(User, ids('teach')))
        assert live.state('users', now=now) == live.state('users', now=now + timedelta(minutes=70))


def test_grading_list_follows_a_draft(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, essay=True)
    cq = give(vq, 'sam')
    from app.qgen import services as S
    S.submit(cq, {1: 'Light makes sugar.'})
    before = poll(teach, 'review')
    cp = cq.cproblems[0]
    cp.credit = 0.5
    db.session.commit()
    assert poll(teach, 'review') != before


def test_one_quizs_results_ignore_other_quizzes(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    a, b = make_quiz(app, teach, 'A'), make_quiz(app, teach, 'B')
    give(a, 'sam')
    page = teach.get('/quiz/results/{}'.format(a.id)).data.decode()
    assert 'data-watch="quizresults:{}"'.format(a.id) in page
    one, every = poll(teach, 'quizresults:{}'.format(a.id)), poll(teach, 'byquiz')
    give(b, 'kim')
    assert poll(teach, 'quizresults:{}'.format(a.id)) == one and poll(teach, 'byquiz') != every
    # a quiz nobody has yet is on Results by quiz too
    before = poll(teach, 'byquiz')
    make_quiz(app, teach, 'C')
    assert poll(teach, 'byquiz') != before


def test_conversation_follows_only_its_student(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    teach.get('/messages/{}'.format(ids('sam')))
    before = poll(teach, 'conversation:{}'.format(ids('sam')))
    teach.post('/messages/send', data={'to': str(ids('kim')), 'body': 'Hi kim'})
    assert poll(teach, 'conversation:{}'.format(ids('sam'))) == before
    teach.post('/messages/send', data={'to': str(ids('sam')), 'body': 'Hi sam'})
    assert poll(teach, 'conversation:{}'.format(ids('sam'))) != before


def test_forms_offer_rather_than_reload(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, essay=True)
    cq = give(vq, 'sam')
    from app.qgen import services as S
    S.submit(cq, {1: 'Light makes sugar.'})
    for url, key in (('/quiz/assign', 'assign'), ('/quiz/review/{}'.format(cq.id), 'grading:{}'.format(cq.id)),
                     ('/quiz/editvquiz/{}'.format(vq.id), 'editquiz:{}'.format(vq.id))):
        page = teach.get(url).data.decode()
        assert 'data-watch="{}"'.format(key) in page and 'data-watch-ask' in page, url
    assert 'data-watch=' not in teach.get('/quiz/makevquiz').data.decode()


def test_poll_cost_doesnt_grow_with_messages(app_db):
    app, db = app_db
    teach = login(app, 'teach')

    def statements(n):
        from app.messages.models import Message
        for i in range(n):
            db.session.add(Message(student_id=ids('sam'), from_teacher=True, body='m{}'.format(i), kind='message', to_all=False))
        db.session.commit()
        count = [0]
        def seen(*a, **k):
            count[0] += 1
        event.listen(db.engine, 'before_cursor_execute', seen)
        try:
            teach.get('/messages/poll?watch=messages')
        finally:
            event.remove(db.engine, 'before_cursor_execute', seen)
        return count[0]
    statements(1)  # the first poll reads a few things once
    assert statements(3) == statements(60)


def test_gone_pages_say_so(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    for url, where in (('/quiz/listuser/999', '/userdet'), ('/quiz/listvq/999', '/quiz/listvq'),
                       ('/quiz/editvquiz/999', '/quiz/listvq'), ('/quiz/results/999', '/quiz/results'),
                       ('/messages/999', '/messages'), ('/quiz/archive/999', '/quiz/archive')):
        r = teach.get(url)
        assert r.status_code == 302 and r.headers['Location'].split('?')[0] == where, url
    # an archived attempt's grading page goes to the archived copy
    cq = give(vq, 'sam')
    teach.post('/quiz/delcq/{}'.format(cq.id))
    assert '/quiz/archive/' in teach.get('/quiz/review/{}'.format(cq.id)).headers['Location']


def test_my_quizzes_badge_stays_until_the_quiz_is_handed_in(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teach)
    teach.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    assert sam.get('/messages/poll').get_json()['quizzes'] == 1
    from app.qgen.models import CQuiz
    cq = CQuiz.query.filter_by(assignee=ids('sam')).one()
    sam.get('/quiz/take/{}'.format(cq.id))  # opened from Home or a notice: still to do
    assert sam.get('/messages/poll').get_json()['quizzes'] == 1
    sam.post('/quiz/take/{}'.format(cq.id), data={})  # handed in
    assert sam.get('/messages/poll').get_json()['quizzes'] == 0


# ---------------------------------------------------------------- finding your way

def student_filter(page):
    """A student page's folder buttons (folderfilter.js data): [(name, [vquiz ids], children)]."""
    import json
    raw = page.split('<script type="application/json" class="folder-filter-tree">')[1].split('</script>')[0]
    def one(n):
        return (n['name'], sorted(int(k[2:]) for k in n['keys']), [one(c) for c in n['children']])
    return [one(n) for n in json.loads(raw)]


def test_menu_marks_where_you_are(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    page = teach.get('/quiz/results').data.decode()
    assert 'href="/quiz/results" class="active" aria-current="page">Results by quiz</a>' in no_titles(page)
    assert re.search(r'<summary class="active">Quizzes</summary>', no_titles(page))
    assert '<a class="skip-link" href="#main">' in no_titles(page) and '<main id="main"' in no_titles(page)


def test_back_goes_where_you_came_from(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    page = teach.get('/quiz/listuser/{}'.format(ids('sam')), headers={'Referer': 'http://localhost/dashboard'}).data.decode()
    assert '<a class="btn btn-secondary" href="/dashboard" data-back><span class="back-label">← Dashboard</span></a>' in no_titles(page)
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert '<a class="btn btn-secondary" href="/people" data-back><span class="back-label">← People</span></a>' in no_titles(page)
    # from another site, or from the page itself: its own Back
    for ref in ('https://evil.example/dashboard', 'http://localhost/quiz/listuser/{}'.format(ids('sam'))):
        page = teach.get('/quiz/listuser/{}'.format(ids('sam')), headers={'Referer': ref}).data.decode()
        assert '← People</span></a>' in page, ref
    # and a student page names the student
    page = teach.get('/quiz/results', headers={'Referer': 'http://localhost/quiz/listuser/{}'.format(ids('sam'))}).data.decode()
    assert "← sam&#39;s student page</span></a>" in page


def test_editing_a_quiz_returns_where_it_started(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    start = 'http://localhost/quiz/results/{}'.format(vq.id)
    page = teach.get('/quiz/editvquiz/{}'.format(vq.id), headers={'Referer': start}).data.decode()
    assert '<input type="hidden" name="next" value="/quiz/results/{}" data-back-next>'.format(vq.id) in page
    r = teach.post('/quiz/editvquiz/{}'.format(vq.id), data={'title': 'Week 1b', 'vplist': vq.vpid_lst.strip('[]'), 'shuffle_order': '',
                                                          'retake_rule': 'best', 'next': '/quiz/results/{}'.format(vq.id)})
    assert r.headers['Location'] == '/quiz/results/{}'.format(vq.id)
    r = teach.post('/quiz/editvquiz/{}'.format(vq.id), data={'title': 'Week 1c', 'vplist': vq.vpid_lst.strip('[]'), 'shuffle_order': '',
                                                          'retake_rule': 'best', 'next': 'https://evil.example/'})
    assert 'evil' not in r.headers['Location']


def test_assign_goes_back_to_the_student_page(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    page = teach.get('/quiz/assign?users={}'.format(ids('sam')),
                     headers={'Referer': 'http://localhost/quiz/listuser/{}'.format(ids('sam'))}).data.decode()
    assert '<input type="hidden" name="next" value="/quiz/listuser/{}">'.format(ids('sam')) in page
    r = teach.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')], 'next': '/quiz/listuser/{}'.format(ids('sam'))})
    assert r.headers['Location'] == '/quiz/listuser/{}'.format(ids('sam'))
    r = teach.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('kim')]}, follow_redirects=True)
    assert 'See its history →' in r.data.decode()


def test_grade_next(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, essay=True)
    from app.qgen import services as S
    first, second = give(vq, 'sam'), give(vq, 'kim')
    S.submit(first, {1: 'Light makes sugar.'})
    S.submit(second, {1: 'Plants eat sun.'})
    page = teach.get('/quiz/review/{}'.format(first.id)).data.decode()
    assert '1 of 2 waiting' in page and 'Finish and grade next' in page
    cp = first.cproblems[0]
    data = {'items-0-cpid': cp.id, 'items-0-credit': '80', 'items-0-feedback': '', 'items-0-highlights': '[]',
            'finalize_next': 'Finish and grade next'}
    r = teach.post('/quiz/review/{}'.format(first.id), data=data)
    assert r.headers['Location'] == '/quiz/review/{}'.format(second.id)
    page = teach.get('/quiz/review/{}'.format(second.id)).data.decode()
    assert '1 of 1 waiting' in page and 'Finish and grade next' not in page


def test_after_handing_in_there_is_no_next_quiz_only_back(app_db):
    """No "Next: ..." link (the user removed it, 2026-10-09): it made the next quiz's start
    card go Back to this one's results instead of the page the student started from."""
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    a, b = make_quiz(app, teach, 'A'), make_quiz(app, teach, 'B essay', essay=True)
    done = give(b, 'sam')
    nxt = give(a, 'sam')
    from app.qgen import services as S
    S.submit(done, {1: 'Light makes sugar.'})
    page = sam.get('/quiz/take/{}'.format(done.id)).data.decode()
    assert 'Handed in!' in page and 'Your teacher is checking' in page
    assert 'Next:' not in page and 'href="/quiz/take/{}"'.format(nxt.id) not in page
    assert '← Home</span></a>' in page
    assert 'instructor' not in page.lower()


def test_names_and_titles_lead_somewhere(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, essay=True)
    cq = give(vq, 'sam')
    from app.qgen import services as S
    S.submit(cq, {1: 'Light makes sugar.'})
    page = teach.get('/quiz/review').data.decode()
    assert 'href="/quiz/listuser/{}"'.format(ids('sam')) in page and 'href="/quiz/results/{}"'.format(vq.id) in page
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert 'href="/messages/{}"'.format(ids('sam')) in page and 'Edit user' in page
    page = teach.get('/quiz/results/{}'.format(vq.id)).data.decode()
    assert 'href="/quiz/editvquiz/{}"'.format(vq.id) in page and 'href="/quiz/viewvquiz/{}"'.format(vq.id) in page


def test_notice_links_say_what_they_open(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teach)
    teach.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    panel = sam.get('/messages/notices').data.decode()
    assert '>Go to the quiz</a>' in panel and '>Open</a>' not in panel


# ---------------------------------------------------------------- nicknames

def test_nicknames(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    from app.user.models import User
    # none: just the name, no brackets
    assert 'sam (' not in teach.get('/userdet').data.decode()
    r = sam.post('/profile/nickname', data={'nickname': '  Sammy   the  Great '})
    assert db.session.get(User, ids('sam')).nickname == 'Sammy the Great'
    for url in ('/userdet', '/quiz/listuser', '/quiz/assign', '/messages', '/quiz/listuser/{}'.format(ids('sam'))):
        assert 'sam (Sammy the Great)' in teach.get(url).data.decode(), url
    assert 'Hi, Sammy the Great!' in sam.get('/home').data.decode()  # the nickname, when there is one
    # too long, or someone else's name: refused, nothing changes
    sam.post('/profile/nickname', data={'nickname': 'x' * 33})
    sam.post('/profile/nickname', data={'nickname': 'KIM'})
    assert db.session.get(User, ids('sam')).nickname == 'Sammy the Great'
    # the apps see it
    from app.api.serialize import user_json
    with app.test_request_context():
        assert user_json(db.session.get(User, ids('sam')))['nickname'] == 'Sammy the Great'
    # cleared: back to just the name
    sam.post('/profile/nickname', data={'clear': '1'})
    assert db.session.get(User, ids('sam')).nickname is None
    sam.post('/profile/nickname', data={'nickname': '   '})
    assert db.session.get(User, ids('sam')).nickname is None
    assert 'sam (' not in teach.get('/userdet').data.decode()


def test_only_you_set_your_nickname(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.user.models import User
    # the teacher's Edit user doesn't touch it, and there's no way to set someone else's
    sam = db.session.get(User, ids('sam'))
    sam.nickname = 'Sammy'
    db.session.commit()
    teach.post('/edituser/{}'.format(ids('sam')), data={'username': 'sam', 'email': '', 'nickname': 'Rude'})
    assert db.session.get(User, ids('sam')).nickname == 'Sammy'
    teach.post('/profile/nickname', data={'nickname': 'Boss'})
    assert db.session.get(User, ids('sam')).nickname == 'Sammy'
    assert db.session.get(User, ids('teach')).nickname == 'Boss'  # teachers can have one too


def test_nickname_change_reaches_open_pages(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    teach.get('/userdet')
    before = poll(teach, 'users')
    sam.post('/profile/nickname', data={'nickname': 'Sammy'})
    assert poll(teach, 'users') != before


# ---------------------------------------------------------------- said simply

def test_student_wording(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teach)
    cq = give(vq, 'sam')
    page = take_page(sam, cq.id).data.decode()
    assert 'value="Hand it in"' in page and "Once you hand it in, you can't change your answers." in page
    mine = sam.get('/mypage').data.decode()
    assert '1 attempt</span>' in mine
    # the teacher's pages keep their own words
    assert 'Hand it in' not in teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()


# ---------------------------------------------------------------- one folder style

def test_every_folder_page_is_drawn_the_same_way(app_db):
    import os
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    make_quiz(app, teach)
    give(__import__('app').qgen.models.VQuiz.query.one(), 'sam')
    pages = {'/mypage': sam, '/userdet': teach, '/quiz/listvp': teach, '/quiz/listvq': teach, '/quiz/archive': teach}
    for url, who in pages.items():
        page = who.get(url).data.decode()
        assert '<div class="folders-layout"' in page and 'class="folder-side"' in page, url
        assert '</svg> Uncategorized' in page and ('</svg> All' in page or '</svg> Everyone' in page) and '+ New folder' in page, url
        assert 'data-fold-key="' in page and 'Expand all' in page, url
    # one name for "in no folder" everywhere on screen
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app')
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith('.html'):
                text = open(os.path.join(folder, name)).read()
                for old in ('Main list', 'Top level', 'No folder'):  # ("Unsorted" is the owner's word inside a folder, 2026-10-13)
                    assert old not in text, (name, old)
    # each page remembers its own folders (Messages no longer shares the Users page's)
    keys = [who.get(url).data.decode().split('data-fold-key="')[1].split('"')[0] for url, who in pages.items()]
    keys.append(teach.get('/messages').data.decode().split('data-fold-key="')[1].split('"')[0])
    assert len(set(keys)) == len(keys)


def test_my_quizzes_shows_every_quiz_with_the_ones_to_do_first(app_db):
    """A folder shows all its quizzes in one list (no To do / Done split): the ones still to
    do first, even when older, then the rest."""
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    a, b = make_quiz(app, teach, 'A'), make_quiz(app, teach, 'B')
    todo, done = give(a, 'sam'), give(b, 'sam')  # B is newer, and handed in
    from app.qgen import services as S
    S.submit(done, {1: '4'})
    page = sam.get('/mypage').data.decode()
    assert page.index('>A</h2>') < page.index('>B</h2>')
    assert 'done-box' not in page and '>To do <' not in page and 'class="box-title">Done<' not in page


# ---------------------------------------------------------------- long lists

def test_results_by_student_in_the_users_folders(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    teach.post('/users/folders', data={'name': '7th grade'})
    from app.user.models import UserFolder
    g7 = UserFolder.query.one()
    teach.post('/users/folders/add', data={'user': ids('sam'), 'to': g7.id})
    page = teach.get('/quiz/listuser?folder={}'.format(g7.id)).data.decode()
    assert 'id="student-{}"'.format(ids('sam')) in page and 'id="student-{}"'.format(ids('kim')) not in page
    # the folders are the Users page's: no making or moving them here
    assert '+ New folder' not in page and 'Folder options' not in page and 'data-drop=' not in page
    assert 'class="state-filter"' in page and 'Waiting for grading' in page
    every = teach.get('/quiz/listuser?folder=all').data.decode()
    assert 'id="student-{}"'.format(ids('kim')) in every and 'id="student-{}"'.format(ids('sam')) in every
    # a change to the folders reaches an open Results by student page
    before = poll(teach, 'students')
    teach.post('/users/folders/add', data={'user': ids('kim'), 'to': g7.id})
    assert poll(teach, 'students') != before


def test_results_by_quiz_in_the_quiz_folders(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    a, b = make_quiz(app, teach, 'A'), make_quiz(app, teach, 'B')
    give(a, 'sam')
    teach.post('/quiz/subjects/quizzes/new', data={'name': 'Fall'})
    from app.qgen.models import VQGroup
    fall = VQGroup.query.one()
    teach.post('/quiz/subjects/quizzes/add', data={'quiz': a.id, 'to': fall.id})
    page = teach.get('/quiz/results?folder={}'.format(fall.id)).data.decode()
    assert 'id="quiz-{}"'.format(a.id) in page and 'id="quiz-{}"'.format(b.id) not in page
    assert 'data-state="out"' in page  # sam hasn't handed it in: "Not handed in yet" finds it
    main = teach.get('/quiz/results?folder=main').data.decode()
    assert 'id="quiz-{}"'.format(b.id) in main and 'id="quiz-{}"'.format(a.id) not in main


def test_a_long_conversation_shows_the_newest(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.messages.models import Message
    for i in range(45):
        db.session.add(Message(student_id=ids('sam'), from_teacher=True, body='note {:02d}'.format(i), kind='message', to_all=False))
    db.session.commit()
    page = teach.get('/messages/{}'.format(ids('sam'))).data.decode()
    assert 'note 44' in page and 'note 05' in page and 'note 04' not in page and 'Show older messages' in page
    page = teach.get('/messages/{}?show=80'.format(ids('sam'))).data.decode()
    assert 'note 00' in page and 'Show older messages' not in page


def test_grading_list_by_quiz(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    a, b = make_quiz(app, teach, 'A', essay=True), make_quiz(app, teach, 'B', essay=True)
    from app.qgen import services as S
    for vq, who in ((a, 'sam'), (b, 'kim'), (a, 'kim')):
        S.submit(give(vq, who), {1: 'Light makes sugar.'})
    page = teach.get('/quiz/review').data.decode()
    assert page.count('<details class="box card grading-group" data-list>') == 2 and '3 waiting, oldest first' in page
    assert page.index('“A”') < page.index('“B”')


def test_dashboard_folds_long_lists_of_people(app_db):
    app, db = app_db
    from app.user.models import User
    now = datetime.now()
    for i in range(10):
        u = User(username='s{}'.format(i), is_admin=False, logged_in=True, last_seen=now)
        u.set_password('pw-for-tests')
        db.session.add(u)
    db.session.commit()
    teach = login(app, 'teach')
    page = teach.get('/dashboard').data.decode()
    assert '<details class="box box-mini more-list" data-more="online"><summary class="small"><span class="fold" aria-hidden="true"></span>+3 more</summary>' in page


def test_a_folder_is_optional_when_making_a_problem_or_quiz(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from test_flow import problem_form
    from app.qgen.models import VProblem, VQuiz
    form = dict(problem_form('numeric', 'Sum', 'What is 2 + 2?', '4', []), subjects_shown='1')
    # no folder chosen: the Helper doesn't ask for one, and it saves into Uncategorized
    hints = teach.post('/quiz/checkvprob', data=form).get_json()['hints']
    assert not any('folder' in h['text'].lower() for h in hints)
    teach.post('/quiz/makevprob', data=form)
    vp = VProblem.query.one()
    assert vp.vpgroups == []
    data = {'title': 'Q', 'vplist': str(vp.id), 'subjects_shown': '1'}
    assert not any('folder' in h['text'].lower() for h in teach.post('/quiz/checkvquiz', data=data).get_json()['hints'])
    teach.post('/quiz/makevquiz', data=data)
    assert VQuiz.query.one().vqgroups == []
    page = teach.get('/quiz/makevquiz').data.decode()
    assert 'Folder <span class="muted small">(optional)</span>' in page and 'name="unsorted"' not in page
    # a bad new folder name is still caught before saving
    hints = teach.post('/quiz/checkvprob', data=dict(form, new_subject='x' * 65)).get_json()['hints']
    assert any('64 characters' in h['text'] for h in hints)


def test_dashboard_assigned_box_opens_the_students_copy(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    cq = give(vq, 'sam')
    page = teach.get('/dashboard').data.decode()
    box = page[page.index('id="dash-out"'):]
    box = box[:box.index('</details>')]
    assert '>Week 1</a></span>' in box and 'data-tip="Open the history of “Week 1”' in box  # the name opens its history; the button their copy
    assert 'href="/quiz/take/{}" title="See sam'.format(cq.id) in box and 's copy of this quiz">Assigned</a>' in box
    assert '>Student page</a>' not in box  # sam's name is the way to their page
    # and it opens: the teacher sees sam's questions (only sam can hand it in)
    assert "Only sam can submit it." in teach.get('/quiz/take/{}'.format(cq.id)).data.decode()


def test_student_page_is_called_that_and_groups_quizzes_by_folder(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    a, b, c = make_quiz(app, teach, 'A'), make_quiz(app, teach, 'B'), make_quiz(app, teach, 'C')
    for vq in (a, b, c):
        give(vq, 'sam')
    teach.post('/quiz/subjects/quizzes/new', data={'name': 'Math'})
    from app.qgen.models import VQGroup
    math = VQGroup.query.one()
    teach.post('/quiz/subjects/quizzes/new', data={'name': 'Fractions', 'parent': math.id})
    frac = VQGroup.query.filter_by(title='Fractions').one()
    teach.post('/quiz/subjects/quizzes/add', data={'quiz': a.id, 'to': math.id})
    teach.post('/quiz/subjects/quizzes/add', data={'quiz': b.id, 'to': frac.id})
    teach.post('/quiz/subjects/quizzes/new', data={'name': 'Empty one'})
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert '<h1>sam&#39;s student page</h1>' in page or "<h1>sam's student page</h1>" in page
    assert '<title>sam' in page and 'student page' in page.split('<title>')[1].split('</title>')[0]
    # one list of their quizzes (each once) with folder buttons: New, In progress, then Math holding
    # A and (in Fractions) B; C is in no folder (Uncategorized, worked out by the page); a folder
    # with none of sam's quizzes isn't a button
    for q in (a, b, c):
        assert page.count('data-fkey="q:{}"'.format(q.id)) == 1
    tree = student_filter(page)
    assert [t[0] for t in tree] == ['New', 'In progress', 'Math']
    assert tree[2][1] == sorted([a.id, b.id]) and tree[2][2] == [('Fractions', [b.id], [])]
    assert all(c.id not in t[1] for t in tree[2:])
    # no quiz folders at all: just the automatic New and In progress
    kim_q = give(c, 'kim')
    page = teach.get('/quiz/listuser/{}'.format(ids('kim'))).data.decode()
    assert [t[0] for t in student_filter(page)] == ['New', 'In progress'] and 'data-fkey="q:{}"'.format(c.id) in page


def test_taking_a_quiz_away_updates_everything(app_db):
    """Archive (the teacher's way to take a quiz away from a student), finished or not: every
    page that showed it, and every score and count built from it, follows."""
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    from app.qgen import services as S
    from app.qgen.models import CQuiz, ArchivedAttempt, QuizFolder
    a, b = make_quiz(app, teach, 'A'), make_quiz(app, teach, 'B')
    first, retake = give(a, 'sam'), None
    S.submit(first, {1: '4'})                       # 100%
    with app.test_request_context():
        retake = S.retake(first)
    S.submit(retake, {1: '5'})                      # 0%: with "best" the score that counts is 100%
    todo = give(b, 'sam')                           # not started
    # sam files A in a folder of their own
    sam.post('/mypage/folders', data={'name': 'Done'})
    folder = QuizFolder.query.filter_by(owner_id=ids('sam')).one()
    sam.post('/mypage/move', data={'quiz': a.id, 'to': folder.id})
    keys = {k: poll(who, k) for who, k in ((sam, 'home'), (sam, 'mine'), (teach, 'students'),
                                            (teach, 'student:{}'.format(ids('sam'))), (teach, 'byquiz'),
                                            (teach, 'quizresults:{}'.format(a.id)))}
    assert '>A</h2>' in sam.get('/mypage?folder={}'.format(folder.id)).data.decode()
    assert 'Perfect score' in sam.get('/home').data.decode()

    # take away the 100% attempt (finished): A's score that counts is now 0%, the perfect-score
    # award goes, and every page that shows them notices
    teach.post('/quiz/delcq/{}'.format(first.id))
    assert ArchivedAttempt.query.filter_by(original_id=first.id).count() == 1
    for (who, k), before in zip(((sam, 'home'), (sam, 'mine'), (teach, 'students'), (teach, 'student:{}'.format(ids('sam'))),
                                 (teach, 'byquiz'), (teach, 'quizresults:{}'.format(a.id))), keys.values()):
        assert poll(who, k) != before, k
    home = sam.get('/home').data.decode()
    assert 'Perfect score' not in home.split('Still to earn')[0]
    results = teach.get('/quiz/results/{}'.format(a.id)).data.decode()
    assert 'Average 0%' in results
    # take away the unfinished one: off Home's "Waiting for you" and the Dashboard's list
    assert '“B”' in home
    teach.post('/quiz/delcq/{}'.format(todo.id))
    assert '“B”' not in sam.get('/home').data.decode()
    dash = teach.get('/dashboard').data.decode()
    assert '/quiz/take/{}'.format(todo.id) not in dash
    # the last attempt at A gone: A leaves sam's folder and My quizzes; the folder stays, empty
    teach.post('/quiz/delcq/{}'.format(retake.id))
    page = sam.get('/mypage?folder={}'.format(folder.id)).data.decode()
    assert '>A</h2>' not in page and CQuiz.query.filter_by(assignee=ids('sam')).count() == 0
    # its notices are gone too (they'd lead nowhere), and sam opening the old address is told
    r = sam.get('/quiz/take/{}'.format(first.id), follow_redirects=True).data.decode()
    assert 'Your teacher has taken this quiz away.' in r
    # all three are in the Archive, in sam's folder, and can be put back
    assert ArchivedAttempt.query.count() == 3


# ---------------------------------------------------------------- folder pages start on All

def test_folder_pages_start_on_all(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    from app.qgen.models import QuizFolder
    a, b = make_quiz(app, teach, 'A'), make_quiz(app, teach, 'B')
    give(a, 'sam'), give(b, 'sam')
    sam.post('/mypage/folders', data={'name': 'Math'})
    folder = QuizFolder.query.filter_by(owner_id=ids('sam')).one()
    sam.post('/mypage/move', data={'quiz': a.id, 'to': folder.id})

    def shown(page):
        return re.search(r'data-view="(\w+)"', page).group(1)
    assert shown(sam.get('/mypage').data.decode()) == 'all'
    # open the folder, go Home, come back from the menu: All again
    page = sam.get('/mypage?folder={}'.format(folder.id)).data.decode()
    assert shown(page) == str(folder.id) and '>A</h2>' in page and '>B</h2>' not in page
    sam.get('/home')
    assert shown(sam.get('/mypage').data.decode()) == 'all'
    # the side list's links say which folder, so "Uncategorized" and "All" can be picked
    assert 'href="/mypage?folder=main"' in page and 'href="/mypage?folder=all"' in page
    # a folder that's gone: All
    sam.post('/mypage/folders/{}/delete'.format(folder.id))
    assert shown(sam.get('/mypage?folder={}'.format(folder.id)).data.decode()) == 'all'
    # the teacher's folder pages too
    teach.get('/quiz/listvq?folder=main')
    for url in ('/quiz/listvq', '/quiz/listvp', '/quiz/archive', '/quiz/listuser', '/userdet'):
        assert shown(teach.get(url).data.decode()) == 'all', url


def test_editors_can_start_over(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    for url, label in (('/quiz/makevprob', 'Start over'), ('/quiz/makevquiz', 'Start over'),
                       ('/quiz/editvquiz/{}'.format(vq.id), 'Undo changes')):
        page = teach.get(url).data.decode()
        assert re.search(r'data-start-over="{}"'.format(re.escape(url)), page), url
        assert '↺ {}</button>'.format(label) in page, url
    # the page it reopens keeps where it was opened from (?next=)
    page = teach.get('/quiz/makevquiz?next=/dashboard').data.decode()
    assert 'data-start-over="/quiz/makevquiz?next=/dashboard"' in page


def test_my_quizzes_lists_the_last_few_handed_in(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    from app.qgen import services as S
    from app.user.routes import LATEST_FINISHED
    page = sam.get('/mypage').data.decode()
    assert 'Just finished' not in page                      # nothing handed in yet
    quizzes = [make_quiz(app, teach, 'Q{}'.format(i)) for i in range(LATEST_FINISHED + 1)]
    attempts = [give(q, 'sam') for q in quizzes]
    for cq in attempts:
        S.submit(cq, {1: '4'})
    page = sam.get('/mypage?folder=main').data.decode()
    top = page.split('id="latest-finished"')[1].split('</section>')[0]
    shown = re.findall(r'<strong>“(Q\d)”</strong>', top)
    assert len(shown) == LATEST_FINISHED and 'Q0' not in shown  # newest first, the oldest left out
    assert '100%' in top and '/quiz/take/{}'.format(attempts[-1].id) in top


def test_home_counters_open_my_quizzes_showing_just_those(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    from app.qgen import services as S
    new, begun, soon, done = (make_quiz(app, teach, t) for t in ('New one', 'Begun', 'Soon', 'Done'))
    give(new, 'sam')
    give(begun, 'sam')
    give(soon, 'sam', closes_at=datetime.now() + timedelta(hours=5))
    S.submit(give(done, 'sam'), {1: '4'})
    from app.qgen.models import CQuiz
    cq = CQuiz.query.filter_by(vquiz_id=begun.id).one()
    cq.startdate = datetime.now()
    db.session.commit()
    home = sam.get('/home').data.decode()
    # New and In progress open My quizzes on the tab of the same name; Due, its quizzes due soon
    assert 'href="/mypage?folder=new"' in home and 'href="/mypage?folder=started"' in home
    assert 'href="/mypage?show=soon"' in home and 'href="/mypage?folder=soon"' not in home
    assert 'data-start="new"' in sam.get('/mypage?folder=new').data.decode()
    new = sam.get('/mypage?folder=new').data.decode()
    assert '“New one”' in new or 'New one' in new
    assert 'Begun' in sam.get('/mypage?folder=started').data.decode()
    assert 'href="#waiting"' not in home

    def titles(show):
        page = sam.get('/mypage?show=' + show).data.decode()
        assert 'data-keep-open' in page and 'Just finished' in page and 'Show all my quizzes' not in page
        return re.findall(r'<h2 title="([^"]+)" class="box-title">', page)
    assert set(titles('todo')) == {'New one', 'Soon'}
    assert titles('started') == ['Begun']
    assert titles('soon') == ['Soon']
    # afterward My quizzes starts on All as always
    sam.get('/mypage?show=todo')
    assert 'data-view="all"' in sam.get('/mypage').data.decode()


# ---------------------------------------------------------------- a Back button on every page

def test_pages_off_the_menu_have_a_back_button(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teach)
    cq = give(vq, 'sam')
    for who, url in ((sam, '/profile'), (teach, '/profile'), (teach, '/settings'), (teach, '/upload'),
                     (teach, '/images'), (teach, '/nonimages'), (teach, '/quiz/assign'),
                     (teach, '/messages/{}'.format(ids('sam'))), (sam, '/quiz/take/{}'.format(cq.id)),
                     (sam, '/no/such/page')):
        page = who.get(url).data.decode()
        assert re.search(r'<a class="btn btn-secondary" href="[^"]+" data-back><span class="back-label">← ', no_titles(page)), url
    # with nowhere better known, My profile goes back to Home (Dashboard for a teacher)
    assert 'href="/home" data-back><span class="back-label">← Home</span></a>' in no_titles(sam.get('/profile').data.decode())
    # the script that points each Back at the page it was opened from is on every page
    assert 'js/trail.js' in sam.get('/profile').data.decode()
    assert 'data-back-href>Cancel</a>' in no_titles(teach.get('/chpass').data.decode())


def test_saving_in_an_editor_goes_back_where_it_was_opened(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    page = teach.get('/quiz/editvquiz/{}'.format(vq.id)).data.decode()
    assert 'data-back-next' in no_titles(page) and 'data-back-href>Cancel</a>' in no_titles(page)
    form = {'title': vq.title, 'vplist': vq.vpid_lst}
    r = teach.post('/quiz/editvquiz/{}'.format(vq.id), data=dict(form, next='/quiz/viewvquiz/{}'.format(vq.id)))
    assert r.status_code == 302 and r.headers['Location'].endswith('/quiz/viewvquiz/{}'.format(vq.id))
    # back to the list: the list as it was left (its view kept), with the quiz lit up
    r = teach.post('/quiz/editvquiz/{}'.format(vq.id), data=dict(form, next='/quiz/listvq?folder=all'))
    assert r.headers['Location'].endswith('/quiz/listvq?folder=all&show={}'.format(vq.id))


def test_home_counter_views_say_what_they_show(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    give(make_quiz(app, teach, 'New one'), 'sam')
    page = sam.get('/mypage?show=todo').data.decode()
    assert '<h2 id="folder-title" class="folder-title">To do: quizzes you haven’t started</h2>' in page
    page = sam.get('/mypage?show=started').data.decode()
    assert '>In progress: quizzes you’ve started, or handed in and not graded yet</h2>' in page
    assert 'Nothing in progress right now. {}'.format(ico('party')) in page
    page = sam.get('/mypage?show=soon').data.decode()
    with app.app_context():
        from app import tuning
        days = tuning.get('due_soon_days')
    within = '{} day{}'.format(days, '' if days == 1 else 's')
    assert '>Due within {}</h2>'.format(within) in page and 'Nothing is due within {}. {}'.format(within, ico('party')) in page
    # the ordinary page's heading is the page's own name (the open tab says which folder)
    assert 'class="folder-title">My quizzes</h2>' in sam.get('/mypage?folder=all').data.decode()


# ---------------------------------------------------------------- removing a quiz, taking one away

def test_removing_an_assigned_quiz_keeps_everything_for_students(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    from app.qgen import services as S
    from app.qgen.models import VQuiz
    vq = make_quiz(app, teach, 'Old quiz')
    cq = give(vq, 'sam')
    S.submit(cq, {1: '4'})
    r = teach.post('/quiz/delvq/{}'.format(vq.id), follow_redirects=True).data.decode()
    assert 'Removed “Old quiz” from Quizzes' in r
    assert db.session.get(VQuiz, vq.id).removed_at is not None
    # off the Quizzes page and Assign; still on My quizzes, Results and the Removed list
    assert 'data-item="{}"'.format(vq.id) not in teach.get('/quiz/listvq?folder=all').data.decode()
    assert 'Removed quizzes (1)' in teach.get('/quiz/listvq').data.decode()
    assert '>Old quiz<' not in teach.get('/quiz/assign').data.decode()
    assert '>Old quiz</h2>' in sam.get('/mypage?folder=all').data.decode()
    assert 'Removed</span>' in teach.get('/quiz/results/{}'.format(vq.id)).data.decode()
    assert 'Old quiz' in teach.get('/quiz/removed').data.decode()
    # brought back
    teach.post('/quiz/removed/{}/back'.format(vq.id))
    assert db.session.get(VQuiz, vq.id).removed_at is None
    assert 'disabled title="No quizzes have been removed">Removed quizzes (0)</button>' in teach.get('/quiz/listvq').data.decode()
    # never assigned: deleted for good, as before
    other = make_quiz(app, teach, 'Unused')
    teach.post('/quiz/delvq/{}'.format(other.id))
    assert db.session.get(VQuiz, other.id).removed_at is not None  # (never assigned too: into the trash bin)


def test_a_quiz_cant_be_removed_while_someone_is_taking_it(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.qgen.models import VQuiz
    vq = make_quiz(app, teach, 'Busy')
    cq = give(vq, 'sam')
    cq.startdate = datetime.now()
    db.session.commit()
    r = teach.post('/quiz/delvq/{}'.format(vq.id), follow_redirects=True).data.decode()
    assert 'Not removed.' in r and 'is taking “Busy” right now' in r
    assert db.session.get(VQuiz, vq.id).removed_at is None
    # its due date has passed: abandoned, not "taking it"
    cq.closes_at = datetime.now() - timedelta(minutes=1)
    db.session.commit()
    teach.post('/quiz/delvq/{}'.format(vq.id))
    assert db.session.get(VQuiz, vq.id).removed_at is not None


def test_take_a_quiz_away_from_a_student_in_one_go(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.qgen import services as S
    from app.qgen.models import CQuiz, ArchivedAttempt
    vq = make_quiz(app, teach, 'Twice')
    first = give(vq, 'sam')
    S.submit(first, {1: '4'})
    with app.test_request_context():
        S.retake(first)
    give(vq, 'kim')
    page = teach.get('/quiz/results/{}'.format(vq.id)).data.decode()
    assert 'Archive all (2)' in page and 'Take away' not in page
    r = teach.post('/quiz/takeaway/{}/{}'.format(vq.id, ids('sam')), follow_redirects=True).data.decode()
    assert 'Archived sam’s 2 attempts at “Twice”. They’re in the' in r
    assert CQuiz.query.filter_by(vquiz_id=vq.id, assignee=ids('sam')).count() == 0
    assert ArchivedAttempt.query.filter_by(student_id=ids('sam')).count() == 2
    assert CQuiz.query.filter_by(vquiz_id=vq.id, assignee=ids('kim')).count() == 1


def test_a_removed_quiz_can_be_deleted_for_good(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.qgen import services as S
    from app.qgen.models import VQuiz, CQuiz, ArchivedAttempt
    vq = make_quiz(app, teach, 'Gone soon')
    S.submit(give(vq, 'sam'), {1: '4'})
    give(vq, 'kim')
    teach.post('/quiz/delvq/{}'.format(vq.id))
    page = teach.get('/quiz/removed').data.decode()
    assert '/quiz/removed/{}/delete'.format(vq.id) in page and '2 attempts leave students’ My quizzes' in page
    r = teach.post('/quiz/removed/{}/delete'.format(vq.id), follow_redirects=True).data.decode()
    assert 'Deleted “Gone soon” for good. Its 2 attempts are in the' in r
    assert db.session.get(VQuiz, vq.id) is None and CQuiz.query.count() == 0
    assert {a.quiz_title for a in ArchivedAttempt.query} == {'Gone soon'} and ArchivedAttempt.query.count() == 2


# ---------------------------------------------------------------- the automatic "New" folder

def test_new_folder_on_my_quizzes_and_the_student_page(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    from app.qgen import services as S
    from app.qgen.models import QuizFolder
    fresh, begun, done = (make_quiz(app, teach, t) for t in ('Fresh', 'Begun', 'Done'))
    give(fresh, 'sam')
    cq = give(begun, 'sam')
    cq.startdate = datetime.now()
    db.session.commit()
    S.submit(give(done, 'sam'), {1: '4'})
    sam.post('/mypage/folders', data={'name': 'Math'})
    folder = QuizFolder.query.filter_by(owner_id=ids('sam')).one()
    sam.post('/mypage/move', data={'quiz': fresh.id, 'to': folder.id})
    page = sam.get('/mypage?folder=main').data.decode()
    # in the side list, with a badge counting what's new
    assert 'href="/mypage?folder=new"' in page and 'side-new-badge" title="1 attempt not started yet">1 new</span>' in page
    # the folder it's filed in says so too, with a small dot (it may be out of sight in another folder)
    assert '<span class="side-dot dot-new" title="1 new attempt" role="img" aria-label="1 new attempt">1</span>' in page
    # and Uncategorized has the started one
    assert '<span class="side-dot dot-started" title="1 attempt in progress" role="img" aria-label="1 attempt in progress">1</span>' in page
    # only the automatic folders carry full badges; the others have dots
    assert 'side-flag"' not in page
    page = sam.get('/mypage?folder=new').data.decode()
    # the New tab holds just it (static/js/folderfilter.js), and its card names its folder
    import json
    tree = json.loads(re.search(r'class="folder-filter-tree">(.*?)</script>', page, re.S).group(1))
    assert [t['keys'] for t in tree if t['id'] == 'new'] == [['quiz:{}'.format(fresh.id)]] and 'data-start="new"' in page
    assert '>New: quizzes you haven’t started</h2>' in page and '</svg> Math</a>' in page
    # still in its own folder
    assert 'Fresh' in sam.get('/mypage?folder={}'.format(folder.id)).data.decode()
    # the teacher's student page: a New folder button with the same quiz, and In progress beside it
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    tree = dict((t[0], t[1]) for t in student_filter(page))
    assert tree['New'] == [fresh.id] and tree['In progress'] == [begun.id]
    # started: no longer new, no badge
    for c in fresh.cquizzes:
        c.startdate = datetime.now()
    db.session.commit()
    mine = sam.get('/mypage').data.decode()
    assert ' new</span>' not in mine.split('<nav aria-label="Folders">')[1].split('</nav>')[0] and '2 in progress</span>' in mine
    assert 'No new quizzes right now.' in sam.get('/mypage?folder=new').data.decode()
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    tree = dict((t[0], t[1]) for t in student_filter(page))
    assert tree['New'] == [] and tree['In progress'] == sorted([fresh.id, begun.id])


def test_a_teacher_taking_a_quiz_gets_the_students_pages(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.qgen import services as S
    vq = make_quiz(app, teach, 'Mine')
    cq = give(vq, 'teach')
    home = teach.get('/home').data.decode()
    assert '“Mine”' in home and 'href="/mypage?folder=new"' in home and 'href="/mypage?folder=started"' in home
    page = teach.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'href="/home" data-back><span class="back-label">← Home</span></a>' in no_titles(page)
    S.submit(cq, {1: '4'})
    page = teach.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'href="/home" data-back><span class="back-label">← Home</span></a>' in no_titles(page) and 'Answer key' not in no_titles(page)
    # taken away: told as a student is, not sent to the Archive
    teach.post('/quiz/delcq/{}'.format(cq.id))
    r = teach.get('/quiz/take/{}'.format(cq.id), follow_redirects=True).data.decode()
    assert 'Your teacher has taken this quiz away.' in r


# ---------------------------------------------------------------- deleting a folder with what's in it

def test_a_student_deletes_a_folder_and_its_quizzes(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    from app.qgen.models import QuizFolder, CQuiz, ArchivedAttempt
    from app.messages.models import Message
    from app.qgen import services as S
    a, b = make_quiz(app, teach, 'A'), make_quiz(app, teach, 'B')
    a_try, _ = give(a, 'sam'), give(b, 'sam')
    sam.post('/mypage/folders', data={'name': 'Old'})
    old = QuizFolder.query.filter_by(owner_id=ids('sam')).one()
    sam.post('/mypage/folders', data={'name': 'Inner', 'parent': old.id})
    inner = QuizFolder.query.filter_by(name='Inner').one()
    sam.post('/mypage/move', data={'quiz': a.id, 'to': inner.id})
    # a quiz in it still to do: not yet, and the page says why
    page = sam.get('/mypage?folder={}'.format(old.id)).data.decode()
    assert 'disabled title="First hand in every quiz in this folder. Still to do: “A”."' in page
    sam.post('/mypage/folders/{}/purge'.format(old.id), data={'view': str(old.id)})
    assert QuizFolder.query.filter_by(owner_id=ids('sam')).count() == 2
    assert CQuiz.query.filter_by(assignee=ids('sam'), vquiz_id=a.id).count() == 1
    S.submit(a_try, {1: '4'})
    page = sam.get('/mypage?folder={}'.format(old.id)).data.decode()
    assert 'Delete folder and everything in it' in page and 'disabled title="First hand in' not in page
    assert 'Delete the folder “Old” and the folders inside it and the 1 quiz in it? It goes to your teacher' in page
    r = sam.post('/mypage/folders/{}/purge'.format(old.id), data={'view': str(old.id)}, follow_redirects=True).data.decode()
    assert 'Deleted the folder &#34;Old&#34; and its 1 quiz' in r or 'Deleted the folder "Old" and its 1 quiz' in r
    assert QuizFolder.query.filter_by(owner_id=ids('sam')).count() == 0
    assert CQuiz.query.filter_by(assignee=ids('sam'), vquiz_id=a.id).count() == 0
    assert CQuiz.query.filter_by(assignee=ids('sam'), vquiz_id=b.id).count() == 1     # not in the folder: kept
    assert ArchivedAttempt.query.filter_by(student_id=ids('sam'), reason='student folder').count() == 1
    assert Message.query.filter(Message.body.like('sam deleted their folder "Old"%')).count() == 1
    # someone else's folder: refused
    teach.post('/mypage/folders', data={'name': 'T'})
    t = QuizFolder.query.filter_by(owner_id=ids('teach')).one()
    sam.post('/mypage/folders/{}/purge'.format(t.id))
    assert db.session.get(QuizFolder, t.id) is not None


def test_a_teacher_deletes_a_problem_or_quiz_folder_and_its_contents(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from test_subjects import make_problems
    from app.qgen.models import VPGroup, VQGroup, VProblem, VQuiz
    probs = make_problems(teach, 'Free', 'Used', 'Shared')
    teach.post('/quiz/makevquiz', data={'title': 'UsesIt', 'vplist': str(probs['Used'].id)})
    teach.post('/quiz/subjects/problems/new', data={'name': 'Unit'})
    teach.post('/quiz/subjects/problems/new', data={'name': 'Elsewhere'})
    unit, elsewhere = VPGroup.query.filter_by(title='Unit').one(), VPGroup.query.filter_by(title='Elsewhere').one()
    teach.post('/quiz/subjects/problems/file', data={'subject': unit.id, 'items': [p.id for p in probs.values()], 'action': 'add'})
    teach.post('/quiz/subjects/problems/file', data={'subject': elsewhere.id, 'items': [probs['Shared'].id], 'action': 'add'})
    page = teach.get('/quiz/listvp?folder={}'.format(unit.id)).data.decode()
    assert '1 problem is deleted for good.' in page and '“Used” (used by “UsesIt”)' in page and '“Shared” (also in “Elsewhere”)' in page
    r = teach.post('/quiz/subjects/problems/{}/purge'.format(unit.id), follow_redirects=True).data.decode()
    assert 'Deleted the folder “Unit”. 1 problem deleted. 2 problems kept, moved up a level.' in r
    assert db.session.get(VPGroup, unit.id) is None
    assert sorted(p.title for p in VProblem.query) == ['Shared', 'Used']
    # a quiz folder: an assigned quiz is removed (students keep it), an unassigned one deleted
    teach.post('/quiz/makevquiz', data={'title': 'Spare', 'vplist': str(probs['Used'].id)})
    used, spare = VQuiz.query.filter_by(title='UsesIt').one(), VQuiz.query.filter_by(title='Spare').one()
    give(used, 'sam')
    teach.post('/quiz/subjects/quizzes/new', data={'name': 'Term 1'})
    term = VQGroup.query.one()
    teach.post('/quiz/subjects/quizzes/file', data={'subject': term.id, 'items': [used.id, spare.id], 'action': 'add'})
    page = teach.get('/quiz/listvq?folder={}'.format(term.id)).data.decode()
    # (every quiz goes to Removed quizzes, the trash bin)
    assert '2 quizzes are taken off the Quizzes page; students keep their copies' in page
    r = teach.post('/quiz/subjects/quizzes/{}/purge'.format(term.id), follow_redirects=True).data.decode()
    assert '2 quizzes removed (students keep their copies).' in r
    assert db.session.get(VQuiz, spare.id).removed_at is not None and db.session.get(VQuiz, used.id).removed_at is not None


def test_dashboard_recent_hand_ins_name_the_quiz_as_a_link_to_its_history(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.qgen import services as S
    vq = make_quiz(app, teach, 'Handed')
    cq = give(vq, 'sam')
    S.submit(cq, {1: '4'})
    page = teach.get('/dashboard').data.decode()
    row = page.split('/quiz/take/{}'.format(cq.id))[0].rsplit('<li>', 1)[1]
    assert 'href="/quiz/results/{}" data-tip="Open the history of “Handed”: everyone’s attempts and scores">Handed</a>'.format(vq.id) in row
    assert 'href="/quiz/listuser/{}" data-tip="Open sam’s student page"'.format(ids('sam')) in row and '>Student page</a>' not in row


def test_dashboard_waiting_for_grading_names_the_quiz_as_a_link_to_its_history(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.qgen.models import CQuiz
    vq = make_quiz(app, teach, 'Essay week')
    cq = give(vq, 'sam')
    cq.needs_review, cq.compdate = True, datetime.now()
    db.session.commit()
    page = teach.get('/dashboard').data.decode()
    row = page.split('/quiz/review/{}'.format(cq.id))[0].rsplit('<li>', 1)[1]
    assert '>Essay week</a>' in row and 'href="/quiz/results/{}"'.format(vq.id) in row and '>Student page</a>' not in row


def test_an_archive_folder_can_be_deleted_for_good(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.qgen import services as S
    from app.qgen.models import ArchivedAttempt, ArchiveFolder
    vq = make_quiz(app, teach, 'Old one')
    for name in ('sam', 'kim'):
        teach.post('/quiz/delcq/{}'.format(give(vq, name).id))
    sam_folder = ArchiveFolder.query.filter_by(student_id=ids('sam')).one()
    page = teach.get('/quiz/archive?folder={}'.format(sam_folder.id)).data.decode()
    assert 'Delete folder and everything in it' in page
    assert 'Delete the folder “sam” and the 1 archived attempt in it for good?' in page
    r = teach.post('/quiz/archive/folders/{}/purge'.format(sam_folder.id), follow_redirects=True).data.decode()
    assert 'Deleted the folder “sam” and its 1 archived attempt.' in r
    assert ArchivedAttempt.query.filter_by(student_id=ids('sam')).count() == 0
    assert ArchivedAttempt.query.filter_by(student_id=ids('kim')).count() == 1
    db.session.expire_all()
    assert db.session.get(ArchiveFolder, sam_folder.id).removed   # out of sight, made again when needed
    teach.post('/quiz/delcq/{}'.format(give(vq, 'sam').id))
    db.session.expire_all()
    assert not db.session.get(ArchiveFolder, sam_folder.id).removed


def test_someone_told_to_change_their_password_can_still_log_out(app_db):
    """On a shared classroom computer a student whose password was reset must be able to leave."""
    app, db = app_db
    from app.user.models import User
    sam = login(app, 'sam')
    u = User.query.filter_by(username='sam').one()
    u.pw_man_reset = True
    db.session.commit()
    assert '/chpass' in sam.get('/home').headers['Location']  # everything else still asks first
    r = sam.get('/logout')
    assert r.status_code == 302 and '/chpass' not in r.headers['Location']
    assert '/login' in sam.get('/home').headers['Location']  # really logged out


def test_uploading_never_replaces_a_file_already_there(app_db):
    import io
    import os
    app, db = app_db
    teach = login(app, 'teach')
    sdir = app.config['STATIC_DIR']

    def up(name, body):
        return teach.post('/upload', data={'thefile': (io.BytesIO(body), name)}, content_type='multipart/form-data',
                          follow_redirects=True).data.decode()
    assert 'Uploaded “notes.txt”.' in up('notes.txt', b'first')
    page = up('notes.txt', b'second')
    assert 'Uploaded “notes.txt” as “notes-2.txt”, since a file called “notes.txt” is already there.' in page
    assert open(os.path.join(sdir, 'notes.txt'), 'rb').read() == b'first'
    assert open(os.path.join(sdir, 'notes-2.txt'), 'rb').read() == b'second'
    # nor a site folder (css, js), nor with a name that can't be used
    os.makedirs(os.path.join(sdir, 'js'), exist_ok=True)
    assert 'as “js-2”' in up('js', b'x')
    assert os.path.isdir(os.path.join(sdir, 'js'))
    assert 'That file name can' in up('..', b'x')


def test_a_quiz_can_be_moved_from_its_heading_any_time_and_stays_in_the_automatic_folders(app_db):
    """Every quiz on My quizzes has "Move… ▾" in its heading (new, started or done), whose list
    moves it at once; moved, it's still in New / In progress."""
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    from app.qgen.models import QuizFolder
    fresh = make_quiz(app, teach, 'Fresh')
    give(fresh, 'sam')
    sam.post('/mypage/folders', data={'name': 'Week 1'})
    wk = QuizFolder.query.filter_by(owner_id=ids('sam')).one()
    page = sam.get('/mypage?folder=new').data.decode()
    head = page[page.index('data-quiz="{}"'.format(fresh.id)):]
    head = head[:head.index('</summary>')]
    assert 'class="move-form move-mini"' in head and 'Uncategorized (here now)' in head
    r = sam.post('/mypage/move', data={'quiz': fresh.id, 'to': wk.id, 'view': 'new', 'from': 'top'}, follow_redirects=True)
    page = r.data.decode()
    assert 'Fresh' in page and '>Week 1 (here now)</option>' in page  # still in New, now in Week 1
    assert 'Fresh' in sam.get('/mypage?folder={}'.format(wk.id)).data.decode()


def test_special_quizzes_and_every_folder_above_them_are_badged(app_db):
    """A quiz new, in progress or due soon has a badge (open or folded), and so has its folder
    and every folder that folder is in."""
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    from app.qgen.models import QuizFolder
    begun, soon = make_quiz(app, teach, 'Begun'), make_quiz(app, teach, 'Soon')
    give(begun, 'sam').startdate = datetime.now()
    give(soon, 'sam', closes_at=datetime.now() + timedelta(hours=3))
    db.session.commit()
    sam.post('/mypage/folders', data={'name': 'Top'})
    top = QuizFolder.query.filter_by(owner_id=ids('sam'), name='Top').one()
    sam.post('/mypage/folders', data={'name': 'Inner', 'parent': top.id})
    inner = QuizFolder.query.filter_by(name='Inner').one()
    for q in (begun, soon):
        sam.post('/mypage/move', data={'quiz': q.id, 'to': inner.id})
    page = sam.get('/mypage?folder={}'.format(top.id)).data.decode()
    side = page.split('<nav aria-label="Folders">')[1].split('</nav>')[0]
    for f in (top, inner):
        row = side[side.index('data-folder="{}"'.format(f.id)):]
        row = row[:row.index('</div>')]
        assert 'dot-started" title="1 attempt in progress"' in row and 'dot-due" title="1 attempt due soon"' in row
        assert 'dot-new" title="1 new attempt"' in row  # Soon isn't started yet
        assert row.index('dot-due') < row.index('dot-started') < row.index('dot-new')  # most urgent first
    cards = sam.get('/mypage?folder={}'.format(inner.id)).data.decode()
    begun_head = cards[cards.index('data-quiz="{}"'.format(begun.id)):]
    assert '>In progress</span>' in begun_head[:begun_head.index('</summary>')]
    soon_head = cards[cards.index('data-quiz="{}"'.format(soon.id)):]
    soon_head = soon_head[:soon_head.index('</summary>')]
    assert '>Due soon</span>' in soon_head and '>New</span>' in soon_head and 'Hand it in by' in soon_head


def test_folder_numbers_count_tries_not_quizzes(app_db):
    """A quiz given twice and not started is 2 new tries, on its folder and the New folder."""
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teach)
    for _ in range(2):
        teach.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    page = sam.get('/mypage?folder=main').data.decode()
    assert '2 attempts not started yet">2 new</span>' in page
    assert '<span class="side-dot dot-new" title="2 new attempts" role="img" aria-label="2 new attempts">2</span>' in page


def test_standard_wording_and_history_buttons(app_db):
    app, db = app_db
    from app.qgen.models import VQuiz
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    # History only once there's some: not on a quiz or problem nobody has taken
    from app.qgen.models import VProblem
    vp = VProblem.query.first()
    assert '>History</a>' not in no_titles(teach.get('/quiz/editvquiz/{}'.format(vq.id)).data.decode())
    assert '>History</a>' not in no_titles(teach.get('/quiz/editvprob/{}'.format(vp.id)).data.decode())
    give(VQuiz.query.one(), 'sam')
    page = no_titles(teach.get('/quiz/editvquiz/{}'.format(vq.id)).data.decode())
    assert 'href="/quiz/results/{}">History</a>'.format(vq.id) in page
    assert 'href="/quiz/problem-results/{}">History</a>'.format(vp.id) in no_titles(teach.get('/quiz/editvprob/{}'.format(vp.id)).data.decode())
    # unchecking everyone says so (Clear is the filter box's)
    for url in ('/userdet', '/quiz/assign'):
        assert 'data-pick="clear">Uncheck all</button>' in no_titles(teach.get(url).data.decode()), url
    # the teachers' messages page: one name, and Back to Messages
    page = no_titles(teach.get('/messages/teachers').data.decode())
    assert 'Teachers’ messages' in page and '← Messages</span></a>' in page and 'Messages with' not in page


def test_pages_come_back_as_they_were_left(app_db):
    """Back to a page with a filter or folders: static/js/keep.js puts back its filter, its
    open boxes and the place on the page (trail.js marks a return with data-came-back)."""
    import os
    app, db = app_db
    teach = login(app, 'teach')
    for url in ('/quiz/listvp', '/quiz/listvq', '/userdet', '/quiz/listuser'):
        assert '/js/keep.js' in teach.get(url).data.decode(), url
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    trail = open(os.path.join(root, 'static', 'js', 'trail.js')).read()
    keep = open(os.path.join(root, 'static', 'js', 'keep.js')).read()
    assert "setAttribute('data-came-back'" in trail and "hasAttribute('data-came-back')" in keep
    assert "addEventListener('pagehide'" in keep and "dispatchEvent(new Event('input'" in keep


def test_score_counted_stays_on_the_page_behind_nginx(app_db):
    """Changing "Score counted" on Results by quiz comes back to Results by quiz, even
    behind nginx (Host without the port, Referer with it), not to the student page."""
    app, db = app_db
    from app.qgen import services as S
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    for _ in range(2):
        S.submit(give(vq, 'sam'), {1: '5'})
    from app.qgen.models import CQuiz
    cq = CQuiz.query.order_by(CQuiz.id.desc()).first()
    r = teach.post('/quiz/retakerule/{}'.format(cq.id), data={'rule': 'latest'},
                   headers={'Host': 'localhost', 'Referer': 'http://localhost:8080/quiz/results?folder=2'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/quiz/results?folder=2'), r.headers['Location']
    page = teach.get('/quiz/results').data.decode()
    assert 'this.form.requestSubmit ? this.form.requestSubmit()' in page  # keeps the place on the page


def test_folder_lists_have_one_order(app_db):
    """Every folder list: All, the automatic ones (New, In progress, Due within...), the
    folders, then Uncategorized (the user moved it last, 2026-10-09); the student page's
    boxes, the All views' boxes and the folder menus in the same order."""
    import re
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teach)
    give(vq, 'sam')
    for kind in ('problems', 'quizzes'):
        teach.post('/quiz/subjects/{}/new'.format(kind), data={'name': 'Fall'})
    def side(page):
        nav = page.split('<nav aria-label="Folders">')[1].split('</nav>')[0]
        return [re.sub(r'\s+', ' ', n).strip() for n in re.findall(r'class="side-link"[^>]*>(?:<span[^>]*>[^<]*</span>)?\s*(?:<svg\b[^>]*>.*?</svg>\s*)?(?:<span class="side-name">)?([^<]+)', nav)]
    for who, url in ((teach, '/quiz/listvp'), (teach, '/quiz/listvq'), (teach, '/userdet'), (teach, '/quiz/listuser'),
                     (teach, '/quiz/results'), (teach, '/quiz/archive')):
        page = who.get(url).data.decode()
        names = side(page)
        assert names[0] != 'Uncategorized' and names[-1] == 'Uncategorized', (url, names)  # All (or Everyone) first
        if url in ('/quiz/listvp', '/quiz/listvq'):
            nav = page.split('<nav aria-label="Folders">')[1]
            assert 0 < nav.index('Fall') < nav.index('Uncategorized'), url
    names = side(sam.get('/mypage').data.decode())
    assert names[0].startswith('All') and names[1] == 'New' and names[2] == 'In progress' and names[3] == 'Uncategorized', names
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    names = [t[0] for t in student_filter(page)]
    assert names.index('New') < names.index('In progress')
    # the folder menus too: All, the folders, Uncategorized
    from app.qgen import services as S
    with app.test_request_context():
        assert [label for _v, label, _n in S.subject_choices('quizzes')] == ['All quizzes', 'Fall', 'Uncategorized']


def test_one_set_of_sizes_and_accessible_controls():
    """app.css: text sizes and corners come from one short set of tokens; no all-caps
    labels; field borders and the new-quiz gold reach 3:1; text on colored fills follows
    the theme; touch screens get finger-sized controls."""
    import os, re
    css = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'css', 'app.css')).read()
    body = css[css.index('  --shadow:'):]
    sizes = set(re.findall(r'\bfont(?:-size)?\s*:\s*[^;}]*?(\d*\.?\d+rem)', body))
    assert not sizes, sizes  # every rem size is a --fs-* token
    ok = {'var(--r-sm)', 'var(--r)', 'var(--r-lg)', '50%', '999px', '0'}
    # (a value per corner is fine when each is one of the set: a file-folder tab's top corners)
    corners = {c for c in re.findall(r'radius\s*:\s*([^;}]*)', body) if not all(part in ok for part in c.strip().split())}
    assert not corners, corners
    assert 'uppercase' not in css
    assert '--field-border: #7d8695' in css and '--new-edge: #b08300' in css
    assert 'border: 1px solid var(--field-border)' in css
    assert 'color: var(--on-ok)' in css and 'color: var(--on-bad)' in css and '--on-ok: #0f1320' in css
    assert '@media (pointer: coarse)' in css and 'min-height: 44px !important' in css


def test_list_items_have_only_buttons(app_db):
    """On every list, an item's actions are buttons: no text link in a row, a Dashboard line or
    a box's heading, and no "More" menus. The one exception: a student's or quiz's name can be
    a name link (to their student page, its history or their messages, with a tooltip), also on a
    box's heading, but never on a folder's heading (it becomes a folder button)."""
    import re
    from app.qgen import services as S
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, essay=True)
    S.submit(give(vq, 'sam'), {1: 'Light makes sugar.'})
    give(vq, 'kim')
    pages = ['/dashboard', '/dashboard/now', '/quiz/review', '/quiz/listvp?folder=all', '/quiz/listvq?folder=all', '/userdet',
             '/quiz/listuser', '/quiz/listuser/{}'.format(ids('sam')), '/quiz/results', '/quiz/results/{}'.format(vq.id), '/messages']
    for url in pages:
        page = teach.get(url).data.decode()
        main = page[page.index('<main'):page.index('</main>')] if '<main' in page else page
        items = re.findall(r'<tr[ >].*?</tr>|<li>.*?</li>|<summary[ >].*?</summary>', main, re.S)
        for item in items:
            # (the folder list down the side is where to go, not an item: its entries are links)
            links = [a for a in re.findall(r'<a [^>]*>', item) if not re.search(r'class="[^"]*\b(btn|side-link|name-link)\b', a)]
            assert not links, (url, links, item[:300])
            names = re.findall(r'<a class="name-link[^"]*" href="([^"]+)" data-tip="([^"]+)"', item)
            assert all(re.match(r'/(quiz/(listuser|results)|messages)/\d+$', h) and tip.startswith(('Open ', 'Read ')) for h, tip in names), (url, names)
            # a name can be a link on a box's heading (a click there opens the link, the box
            # stays), but not on a folder's heading: that becomes a folder button
            if item.startswith('<summary class="sub-head"'):
                assert 'name-link' not in item, (url, item[:300])
        assert 'row-menu' not in main and 'person-link' not in main, url


def test_folders_on_top_and_their_contents_below(app_db):
    """Side-by-side folder boxes become one row of folder buttons (static/js/foldertabs.js),
    so a folder is never listed below another folder's things (the user, 2026-10-09). Every
    folder list page loads it; folder boxes start closed; Expand all leaves the rows alone."""
    import os
    app, db = app_db
    teach = login(app, 'teach')
    for url in ('/quiz/listvp', '/quiz/listvq', '/userdet', '/quiz/listuser', '/quiz/results', '/quiz/archive', '/mypage'):
        assert 'js/foldertabs.js' in teach.get(url).data.decode(), url
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(here, 'static', 'js', 'foldertabs.js')).read()
    assert "details.sub-box[data-sub], details.sub-box[data-folder-box]" in js
    assert "'qgen-filtered'" in js and 'tabs-off' in js and "data-drop" in js
    # where the folders end and the folder's own things begin (the user, 2026-10-09): the row
    # is labeled "Folders", and a heading ("Problems in “Arithmetic” itself") comes after it
    assert "folder-tabs-label" in js and "folder-items-head" in js and ": Unsorted'" in js
    assert 'data-units="' in teach.get('/userdet').data.decode()
    boxes = open(os.path.join(here, 'static', 'js', 'boxes.js')).read()
    # folders wait to be picked, except the first in a top-level row, while nothing about that row
    # is remembered (an All view never starts as only folder buttons)
    assert "if (d.matches(FOLDER)) {" in boxes and "if (d.parentElement.closest(FOLDER)) return false;" in boxes
    assert "return row[0] === d && !row.some(function (b) { return idOf(b) in memory; });" in boxes
    assert "row.qgenExpanded = true" in js  # Expand all shows every folder open; Collapse all brings the buttons back
    css = open(os.path.join(here, 'static', 'css', 'app.css')).read()
    assert '.folder-tabs:not(.tabs-off) ~ details.tab-box:not([open]) { display: none; }' in css


def test_drawn_icons_everywhere_and_no_emoji():
    """The site's icons are drawn (app/icons.py), chosen over emoji (2026-10-09): every icon
    a template names exists, and no emoji is left in the pages, the code that fills them or
    the page scripts. Text symbols stay (✓ ✕ ✗ ◐ ○ ★), and so do the tab title's 🟡/🔵
    dots, since a tab's title can only hold text."""
    import os
    from app.icons import PATHS
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    emoji = re.compile('[\U0001F300-\U0001FAFF☀-➿⭐⏰-⏿\U0001F100-\U0001F1FF]')
    keep = set('✓✕✗◐○★✔✖')
    named, found = set(), []
    for top in ('app', os.path.join('static', 'js')):
        for dp, _dn, files in os.walk(os.path.join(here, top)):
            for f in files:
                if not f.endswith(('.html', '.py', '.js')):
                    continue
                path = os.path.join(dp, f)
                text = open(path, encoding='utf8').read()
                if f.endswith('.html'):
                    named |= set(re.findall(r"""\b(?:icon|box_label|pick_group\('[^']*',)\s*\(?\s*'([a-z]+)'""", text))
                    text = re.sub(r'\{#.*?#\}', '', text, flags=re.S)  # notes for programmers
                for i, line in enumerate(text.splitlines(), 1):
                    if line.lstrip().startswith(('#', '//', '/*', '*')) or '<title>' in line:
                        continue
                    left = [c for c in emoji.findall(line) if c not in keep]
                    if left:
                        found.append('{}:{}: {}'.format(os.path.relpath(path, here), i, ''.join(left)))
    assert not found, found
    assert named and named <= set(PATHS), named - set(PATHS)


def test_a_folder_above_the_one_youre_in_cant_be_folded():
    """Inside a folder, the folders above it in the folder list can't be folded (the user,
    2026-10-09: the folder you were in vanished from the list)."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(here, 'static', 'js', 'folders.js')).read()
    assert 'path.slice(0, -1)' in js and 'btn.disabled = true' in js and 'so it stays open' in js
    assert '.side-fold:disabled' in open(os.path.join(here, 'static', 'css', 'app.css')).read()


def test_teacher_menu_fits_one_line(app_db):
    """The teacher's top menu (U1, 2026-10-09): Dashboard, Problems, Quizzes, Grading, People
    and More (Archive, Files, Settings); their own Home and My quizzes are under their name
    (its count on the name too); no Messages link (the Messages button at the top right). A
    student's menu keeps Home and My quizzes."""
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    page = no_titles(teach.get('/dashboard').data.decode())
    nav = page.split('<nav class="nav')[1].split('</nav>')[0]
    top, name_menu = nav.split('<div class="nav-right">')
    for label in ('>Dashboard</a>', '>People</a>', '>More</summary>', '>Problems</summary>', '>Quizzes</summary>', 'Grading'):
        assert label in top, label
    assert '>Messages</a>' not in nav and '>Home</a>' not in top and 'My quizzes' not in top
    more = top.split('>More</summary>')[1]
    for label in ('>Archive</a>', '>Upload files</a>', '>Pictures</a>', '>Other files</a>', '>Settings</a>'):
        assert label in more, label
    assert 'My quizzes' in name_menu and '>Home</a>' in name_menu and 'class="count nav-quizzes"' in name_menu.split('</summary>')[0]
    student = no_titles(sam.get('/home').data.decode()).split('<nav class="nav')[1].split('<div class="nav-right">')[0]
    assert '>Home</a>' in student and 'My quizzes' in student and '>More</summary>' not in student


def test_kid_friendly_review_batch(app_db):
    """The second UI review (2026-10-09), items 1, 2, 4, 5, 6, 13 and 14: big answer cards, 14px
    status words, one way of writing dates, the nickname in the greeting, "In progress",
    a plainer More menu, and a solid focus outline."""
    import os
    app, db = app_db
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = open(os.path.join(here, 'static', 'css', 'app.css')).read()
    # 14: the focus outline is solid (a see-through one was about 1.75:1 on white)
    assert 'outline: 3px solid var(--accent);  /* solid' in css and 'var(--accent) 35%, transparent);\n  outline-offset' not in css
    # 1: a quiz's answers are whole-card buttons at least 48px tall
    assert '.question .choice-list label { align-self: stretch; display: flex; align-items: center; padding: 12px 14px 12px 12px; min-height: 48px; }' in css
    # 2: status words are 14px
    assert 'display: inline-block; font-size: var(--fs-sm); font-weight: 600; line-height: 1;' in css
    # 4: every date goes through the |when filter: no hand-written formats in the pages
    for dp, _dn, files in os.walk(os.path.join(here, 'app')):
        for f in files:
            if f.endswith('.html'):
                assert '.strftime(' not in open(os.path.join(dp, f)).read(), f
    from app import when_filter
    from datetime import datetime
    assert when_filter(datetime(2026, 10, 9, 16, 22)) == 'Fri Oct 9, 4:22 PM'
    assert when_filter(datetime(2025, 10, 7, 9, 5), 'short') == 'Tue Oct 7, 2025'
    # 5 and 6: the greeting and the badge a child sees
    from app.user.models import User
    db.session.get(User, ids('sam')).nickname = 'Sammy'
    db.session.commit()
    sam = login(app, 'sam')
    assert 'Hi, Sammy!' in sam.get('/home').data.decode()
    # 13: the More menu: lines between groups, plain names
    teach = login(app, 'teach')
    more = teach.get('/dashboard').data.decode().split('>More</summary>')[1].split('</details>')[0]
    assert more.count('<hr class="menu-rule">') == 2 and '>Upload files</a>' in more and '>Pictures</a>' in more and 'menu-label' not in more
    assert '<h1>Pictures</h1>' in teach.get('/images').data.decode()
    # 15 and 16: the quiz builder's problem boxes have names; the "?" buttons are 24px
    from test_flow import problem_form
    teach.post('/quiz/makevprob', data=problem_form('numeric', 'Sum', 'What is 2 + 2?', '4', []))
    assert 'aria-label="Include “Sum”"' in teach.get('/quiz/makevquiz').data.decode()
    assert 'width: 24px; height: 24px; min-height: 0; padding: 0; margin-left: 2px;' in css


def test_the_messages_page_has_a_way_back(app_db):
    """The Messages page left the menu (2026-10-09), so it has a Back button: to the page you
    came from, else the Dashboard."""
    app, db = app_db
    teach = login(app, 'teach')
    page = no_titles(teach.get('/messages').data.decode())
    assert '<a class="btn btn-secondary" href="/dashboard" data-back><span class="back-label">← Dashboard</span></a>' in page
    page = no_titles(teach.get('/messages', headers={'Referer': 'http://localhost/quiz/listvq'}).data.decode())
    assert '<a class="btn btn-secondary" href="/quiz/listvq" data-back><span class="back-label">← Quizzes</span></a>' in page


def test_side_panels_slide_over_the_page_unless_pinned(app_db):
    """Notices and Messages start closed and slide over the page, so it keeps its whole width;
    the pin in a panel's heading keeps them beside the page instead, as they were left."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app, db = app_db
    page = login(app, 'teach').get('/dashboard').data.decode()
    assert page.count('class="dock-pin"') == 2 and 'aria-pressed="false"' in page
    start = page[page.index('/* the side panels start closed'):page.index('})();', page.index('/* the side panels start closed'))]
    assert "localStorage.getItem('qgen-dock-pinned') === '1'" in start and 'roomy' not in start
    assert "if (pinned && wide) {" in start  # only pinned panels open by themselves
    css = open(os.path.join(here, 'static', 'css', 'app.css')).read()
    assert 'html:not(.dock-pinned) .dock { z-index: 30;' in css
    assert 'html.dock-pinned.dock-notices body, html.dock-pinned.dock-messages body { padding-right: var(--dock-w); }' in css
    js = open(os.path.join(here, 'static', 'js', 'messages.js')).read()
    assert "if (pinned()) store('qgen-dock-' + p, open ? 'open' : 'closed');" in js
    # a click on the page closes them, but not the click that opened them (e.g. "Message students")
    assert 'if (justOpened || pinned() ||' in js and "if (e.key !== 'Escape' || pinned()) return;" in js
    # ...nor a click in the top menus, and Messages stays open while a reply is half-written;
    # loaded again (reopened, a new message), it shows what's new and puts the reply back, as long
    # as it's the same conversation; a pop-up switching to another conversation asks first
    assert "nav.nav, details.menu, .floating-menu" in js and "!(q === 'messages' && busyTyping())" in js
    assert "if (typing && typing.view === view) {" in js and "if (t) t.value = typing.text;" in js
    assert "if (k in typing.checks) i.checked = typing.checks[k];" in js  # its "Send to" / "Pin it" choices too
    assert "if (!view || !busyTyping() || view === drawnView) { go(!!view); return; }" in js


def test_results_rows_are_one_line_tall(app_db):
    """A results row's buttons sit side by side where there's room (each student one line,
    not three stacked buttons), and "Archive all" says how many in brackets."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app, db = app_db
    css = open(os.path.join(here, 'static', 'css', 'app.css')).read()
    assert 'td.actions .btn-stack { flex-direction: row; flex-wrap: wrap; justify-content: flex-end; align-items: center; }' in css
    # an attempt's own line never wraps where the list is wide: the row's buttons stack instead
    assert '@media (min-width: 641px) { .btn-row.result-attempt-buttons { flex-wrap: nowrap; } }' in css
    # ...and narrow pages without a folder list (a quiz's history, one student) wrap by the page's width
    tail = css[css.index('@container page (max-width: 1080px) {\n  td.attempts { white-space: normal; }'):]
    assert '.btn-row.result-attempt, .btn-row.result-attempt-buttons { flex-wrap: wrap; }' in tail
    assert '@container listarea (max-width: 1080px) { td.actions .btn-stack { flex-direction: column; align-items: flex-end; } }' in css
    tpl = open(os.path.join(here, 'app', 'qgen', 'templates', '_results.html')).read()
    assert "'Archive all (' ~ g.attempts|length ~ ')'" in tpl and "slot('Archive all (1)', 'Only one attempt: use its own Archive button', 'btn btn-secondary btn-sm btn-all')" in tpl


def test_a_folded_student_says_where_they_are(app_db):
    """Results by student: each student's folded heading shows quizzes done (and the average),
    to grade, in progress and not started, so the list says something before any click."""
    app, db = app_db
    from test_dashboard import make_quiz, give
    from app.qgen import services as S
    teacher = login(app, 'teach')
    vq = make_quiz(app, teacher)
    with app.test_request_context():
        S.submit(give(vq, 'sam'), {1: '4'})
        give(vq, 'sam')
        db.session.commit()
    page = teacher.get('/quiz/listuser').data.decode()
    sam = page[page.index('id="student-{}"'.format(ids('sam'))):]
    head = sam[:sam.index('</summary>')]
    assert '1 done · avg 100%' in head and '1 not started' in head and 'to grade' not in head
    # colored like every other score: green from 70%, amber from 50%, red below
    assert 'class="badge badge-ok" title="Quizzes with a score that counts' in head
    with app.test_request_context():
        S.submit(give(vq, 'kim'), {1: '5'})
        db.session.commit()
    page = teacher.get('/quiz/listuser').data.decode()
    kim = page[page.index('id="student-{}"'.format(ids('kim'))):]
    assert 'class="badge badge-bad" title="Quizzes with a score that counts, and the average of those scores">1 done · avg 0%' in kim[:kim.index('</summary>')]
    # a retake counts once, by the quiz's rule (best attempt), like the score shown inside the box
    with app.test_request_context():
        S.submit(give(vq, 'kim'), {1: '4'})
        db.session.commit()
    page = teacher.get('/quiz/listuser').data.decode()
    kim = page[page.index('id="student-{}"'.format(ids('kim'))):]
    assert '1 done · avg 100%' in kim[:kim.index('</summary>')]
    emma = page[page.index('id="student-{}"'.format(ids('teach'))):]
    assert 'student-sums' not in emma[:emma.index('</summary>')]  # nothing given: nothing to say


def test_uncategorized_everywhere(app_db):
    """What isn't in any folder is "Uncategorized", on every page (the teacher chose the word)."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app, db = app_db
    teacher = login(app, 'teach')
    from app.qgen import services as S
    make_quiz(app, teacher)
    S.subject_named('quizzes', 'Week 1')  # "Uncategorized" shows beside folders
    for url in ('/quiz/listvp', '/quiz/listvq', '/userdet', '/quiz/assign', '/quiz/makevquiz', '/messages', '/mypage'):
        page = teacher.get(url).data.decode()
        assert 'not in a folder' not in page.lower(), url
    assert 'Uncategorized' in teacher.get('/quiz/listvq').data.decode()
    for root, _, files in os.walk(os.path.join(here, 'app')):
        for f in files:
            if f.endswith(('.html', '.py')):
                assert 'not in a folder' not in open(os.path.join(root, f)).read().lower(), f


def test_where_an_attempt_is_stands_out(app_db):
    """"Not started" (gold) and "In progress" (blue) are outlined in their own color wherever an
    attempt's state is shown, so they stand out among the plain badges beside them."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = open(os.path.join(here, 'static', 'css', 'app.css')).read()
    assert '.badge-status { box-shadow: inset 0 0 0 1px color-mix(in srgb, currentColor 60%, transparent); font-weight: 700; }' in css
    for root, _, files in os.walk(os.path.join(here, 'app')):
        for f in files:
            if f.endswith('.html'):
                text = open(os.path.join(root, f)).read()
                assert '<span class="badge">Not started</span>' not in text, f
                assert '<span class="badge badge-accent">In progress</span>' not in text, f
    app, db = app_db
    teacher = login(app, 'teach')
    vq = make_quiz(app, teacher)
    with app.test_request_context():
        give(vq, 'sam')
        db.session.commit()
    page = teacher.get('/quiz/results/{}'.format(vq.id)).data.decode()
    assert '<span class="badge badge-warn badge-status">Not started</span>' in page


def test_unused_buttons_are_grayed_out_not_missing(app_db):
    """A button that doesn't apply to an item is there, grayed out, saying why (the teacher's rule,
    2026-10-10): no hidden placeholders and no missing buttons on rows of the same kind."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    macros = open(os.path.join(here, 'app', 'templates', '_macros.html')).read()
    assert '{% macro slot(label, why, cls=\'btn btn-secondary btn-sm\') %}<button type="button" class="{{ cls }}" disabled title="{{ why }}">{{ label }}</button>{% endmacro %}' in macros
    css = open(os.path.join(here, 'static', 'css', 'app.css')).read()
    assert '.slot-empty' not in css
    app, db = app_db
    teacher = login(app, 'teach')
    vq = make_quiz(app, teacher)
    with app.test_request_context():
        give(vq, 'sam')
        db.session.commit()
    from test_flow import problem_form
    from app.qgen.models import VProblem
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'Unused', 'What is 3 + 3?', '6', []))
    vp = VProblem.query.filter_by(title='Unused').one()  # in no one's quiz yet
    pages = {
        '/quiz/viewvprob/{}'.format(vp.id): ['disabled title="No one has answered this problem yet">History</button>'],
        '/quiz/editvprob/{}'.format(vp.id): ['disabled title="No one has answered this problem yet">History</button>'],
        '/quiz/results/{}'.format(vq.id): ['disabled title="Nothing to grade: not handed in yet">Grade</button>',
                                           'disabled title="Only one attempt: use its own Archive button">Archive all (1)</button>',
                                           'disabled title="This quiz has no Paper only questions"'],
        '/quiz/review': ['disabled title="Nothing is waiting for grading">Grade the oldest</button>'],
        '/profile': ['disabled title="You don’t have a nickname">Remove nickname</button>'],
        '/settings/technical': ['disabled title="Already the default">Reset</button>'],
        '/userdet': ['disabled title="You can’t delete your own account">Delete</button>',
                     'title="Teachers write to each other in Teachers’ messages">Message</a>'],
    }
    for url, wanted in pages.items():
        page = teacher.get(url).data.decode()
        for w in wanted:
            assert w in page, (url, w)
    # the same states in the same words everywhere a teacher looks
    for root, _, files in os.walk(os.path.join(here, 'app')):
        for f in files:
            if f.endswith('.html'):
                text = open(os.path.join(root, f)).read()
                assert 'Being graded' not in text and '>Not handed in</span>' not in text, f


def test_tidy_layouts_at_every_width(app_db):
    """The rules from the 2026-10-12 sweep of every page at 17 widths: no page scrolls sideways
    and no group of buttons leaves one alone on a line (checked in a browser; these keep the rules)."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = open(os.path.join(here, 'static', 'css', 'app.css')).read()
    for rule in ('a.btn[data-back] .back-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }',
                 '.person-card .btn-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(8.5rem, 1fr)); gap: 6px; }',
                 '.history-table thead { display: none; }',
                 '.keypad { display: grid; grid-template-columns: repeat(4, 1fr); }',
                 '.pick-table td { overflow-wrap: anywhere; }',
                 '.btn-row:has(> .btn ~ .btn ~ .btn):not(.result-attempt):not(.result-attempt-buttons):not(.box-links) { display: grid; grid-template-columns: 1fr; }'):
        assert rule in css, rule
    tpl = open(os.path.join(here, 'app', 'qgen', 'templates', '_results.html')).read()
    assert 'result-archive-all' not in tpl and '{% if archive_all %}{{ archive_all_button(g, student) }}{% endif %}' in tpl  # beside Retake, no row of its own


def test_every_folder_with_boxes_inside_has_its_own_expand_collapse(app_db):
    """A folder box holding boxes of its own (sub-folders, quizzes, attempts) gets Expand all /
    Collapse all for what's inside it, on its heading line (boxes.js adds the pair where the page
    drew none; it shows only with two or more boxes inside). A click there doesn't fold the box,
    and Expand all opens it too. In a row of folder buttons the open folder's pair sits at the
    row's right end (foldertabs.js). The student box's own pair is on its heading too."""
    import os
    app, db = app_db
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(here, 'static', 'js', 'boxes.js')).read()
    assert "document.querySelectorAll('details.sub-box').forEach(function (d) {" in js
    assert "return p.closest('details.sub-box') === d;" in js  # a folder that already has one keeps it
    assert "bar.className = 'head-pair';" in js and "head.appendChild(bar);" in js
    assert "open.dataset.levelOf = close.dataset.levelOf = '#' + body.id;" in js
    assert "var head = btn.closest('summary');" in js and "e.preventDefault();" in js and "head.parentElement.open = true;" in js
    tabs = open(os.path.join(here, 'static', 'js', 'foldertabs.js')).read()
    assert "c.classList.contains('head-pair')" in tabs and "pairsOf(row).appendChild(c);" in tabs
    assert "pair.hidden = searching ? false : !(d.open && !d.hidden);" in tabs
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    give(vq, 'sam')
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    head = page[page.index('id="student-{}"'.format(ids('sam'))):]
    head = head[:head.index('</summary>')]
    assert '<span class="head-pair"><span class="level-buttons">' in head and 'data-level="open"' in head
    assert 'quiz-box-bar' not in page


def test_quiz_boxes_on_a_student_page_line_their_buttons_up(app_db):
    """A student page's quiz boxes share one set of column widths (score and Retake columns fixed,
    attempts the rest) and an attempt's "Results"/"Assigned" button has one width, so the buttons
    of quiz boxes at one folder level sit under one another, two by two included. "Archive all"
    looks different from an attempt's own buttons."""
    import os
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    give(vq, 'sam')
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert 'class="btn btn-secondary btn-sm attempt-open"' in page and '>Assigned</a>' in page
    assert '<thead><tr><th>Attempts</th><th>Score counted</th><th></th></tr></thead>' in page
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = open(os.path.join(here, 'static', 'css', 'app.css')).read()
    assert '.result-box > .table-wrap > table { table-layout: fixed; width: 100%; }' in css
    assert '.result-box > .table-wrap > table > thead th:nth-child(2) { width: 16rem; }' in css
    assert '.result-attempt-buttons .attempt-open { min-width: 5.5rem; text-align: center; }' in css
    assert '@container page (max-width: 1240px) { .btn-row.result-attempt-buttons { margin-left: auto; } }' in css
    # "Archive all" acts on every attempt: its own look, on the quiz's heading line
    assert 'class="btn btn-secondary btn-sm btn-all" disabled title="Only one attempt' in page
    assert '.btn.btn-all { background: var(--surface-2); border-style: dashed;' in css
    # with two attempts it's the real button, with the same look
    give(vq, 'sam')
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    # (a button on the heading sending a form kept outside the heading: no form inside a summary)
    form_id = 'archive-all-{}-{}'.format(ids('sam'), vq.id)
    assert '<button class="btn btn-secondary btn-sm btn-all" form="{}" title="Move every one of sam'.format(form_id) in page and '>Archive all (2)</button>' in page
    assert 'id="{}" class="inline-form" hidden'.format(form_id) in page


def test_assign_says_who_gets_the_quiz(app_db):
    """Coming from People with students checked, Assign names them at the top of the Students card
    ("Assignee", one chip each with a ✕); the list itself never folds, like the Quiz card's."""
    app, db = app_db
    teach = login(app, 'teach')
    page = teach.get('/quiz/assign?users={}&users={}'.format(ids('sam'), ids('kim'))).data.decode()
    top = page[page.index('id="recipients"'):page.index('id="pick-people"')]
    assert '<span class="label">Assignee</span>' in top
    assert '<span class="person-chip" data-user="{}">sam<button type="button" class="chip-x" aria-label="Leave sam out"'.format(ids('sam')) in top
    assert 'data-user="{}">kim<'.format(ids('kim')) in top and 'recipient-none' not in top
    assert 'class="pick-wrap' not in page and 'change who gets it' not in page
    page = teach.get('/quiz/assign').data.decode()
    assert 'Nobody yet: check the students below.' in page
    # "below" is true: Assignee sits above the student list, in the same card
    assert page.index('id="recipients"') < page.index('id="pick-people"') < page.index('name="users"')


def test_a_folders_own_things_have_a_divider_and_their_own_expand_collapse():
    """Where a folder's folders end and its own things begin there's a line ("People in “8th
    Grade” itself"), also while the folders show as boxes; on it, Expand all / Collapse all for
    just those things (not the folders above), which leaves the folder rows alone."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tabs = open(os.path.join(here, 'static', 'js', 'foldertabs.js')).read()
    boxes = open(os.path.join(here, 'static', 'js', 'boxes.js')).read()
    css = open(os.path.join(here, 'static', 'css', 'app.css')).read()
    assert "btn.dataset.levelItems = '';" in tabs and "head.appendChild(pair);" in tabs
    assert "if (!btn || 'levelItems' in btn.dataset) return;" in tabs
    assert "if ('levelItems' in btn.dataset) {" in boxes and "var list = [], head = btn.closest('.folder-items-head');" in boxes
    assert '.folder-tabs.tabs-off ~ .folder-items-head { display: none; }' not in css
    assert '.folder-items-head .level-buttons { margin-left: auto;' in css
    # a tabbed folder's pair goes back on its own heading while the folders show as boxes
    assert "if (searching && pair.parentElement !== head) head.appendChild(pair);" in tabs


def test_set_wide_controls_sit_on_the_heading_line(app_db):
    """Controls for a whole box go on its heading line, not a row of their own: a folder's
    Expand all / Collapse all / Open this folder (folder pages), a student-page quiz's
    "Archive all", Results by quiz's View / Edit / Print, and Results by student's Message /
    Assign; the quiz's or student's name on the heading is the link to its history or student
    page. And never two Expand/Collapse pairs for the same boxes."""
    import os, re
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach)
    give(vq, 'sam'); give(vq, 'sam')
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    box = page[page.index('data-quiz-box='):]
    head = box[:box.index('</summary>')]
    assert 'class="name-link" href="/quiz/results/{}"'.format(vq.id) in head and '>History</a>' not in head and '>Archive all (2)</button>' in head
    assert '<form' not in head and 'result-archive-all' not in box[:box.index('</details>')]
    page = teach.get('/quiz/results').data.decode()
    head = page[page.index('id="quiz-{}"'.format(vq.id)):]
    head = head[:head.index('</summary>')]
    assert '<span class="box-actions">' in head and '>View quiz</a>' in head and '>Edit quiz</a>' in head and '>History</a>' not in head
    assert 'class="name-link" href="/quiz/results/{}"'.format(vq.id) in head
    assert 'box-links' not in page[page.index('<main'):]
    page = teach.get('/quiz/listuser').data.decode()
    head = page[page.index('id="student-{}"'.format(ids('sam'))):]
    head = head[:head.index('</summary>')]
    assert '<span class="box-actions">' in head and '>Student page</a>' not in head and '>Assign a quiz</a>' in head
    assert 'class="name-link" href="/quiz/listuser/{}"'.format(ids('sam')) in head
    folders = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'templates', '_folders.html')).read()
    assert "<span class=\"head-pair\">{{ level_buttons(fk.name(n.folder), of='#folder-body-' ~ f.id) }}" in folders and 'sub-tools' not in folders
    js = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'js', 'boxes.js')).read()
    assert 'if (same) pair.hidden = true;' in js  # a pair for the same boxes as one before it is left out
    assert "setTimeout(function () { if (d.open !== was) d.open = was; }, 0);" in js  # heading buttons don't fold the box


def test_grading_tables_line_their_buttons_up():
    """Grading: every quiz's table has the same column widths, so Grade buttons line up."""
    import os
    css = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'css', 'app.css')).read()
    assert '.grading-group > .table-wrap > table { table-layout: fixed; width: 100%; }' in css
    assert '.grading-group > .table-wrap > table > thead th:nth-child(4) { width: 6.5rem; }' in css


def test_folder_pages_open_on_all(app_db):
    """A folder page's All view is one list, each thing once (no copies: no id twice), with the
    folder buttons above it (static/js/folderfilter.js): All first, then the folders with the keys
    of what's in each (sub-folders included), then Uncategorized worked out by the page."""
    import json, re
    from app.qgen.models import VQGroup, VQuiz
    app, db = app_db
    teach = login(app, 'teach')
    teach.post('/quiz/subjects/quizzes/new', data={'name': 'Week 1'})
    week = VQGroup.query.filter_by(title='Week 1').one()
    teach.post('/quiz/subjects/quizzes/new', data={'name': 'Day 2', 'parent': week.id})
    day = VQGroup.query.filter_by(title='Day 2').one()
    make_quiz(app, teach, 'Filed one')
    make_quiz(app, teach, 'Loose one')
    filed = VQuiz.query.filter_by(title='Filed one').one()
    teach.post('/quiz/subjects/quizzes/file', data={'subject': day.id, 'items': [filed.id]})
    page = teach.get('/quiz/listvq?folder=all').data.decode()
    assert 'data-folder-filter data-prefix="quiz:"' in page and 'class="box sub-box' not in page
    assert page.count('data-box="quiz:{}"'.format(filed.id)) == 1  # once, though it's in a folder
    tree = json.loads(re.search(r'<script type="application/json" class="folder-filter-tree">(.*?)</script>', page, re.S).group(1))
    assert [(n['name'], n['keys']) for n in tree] == [('Week 1', ['quiz:{}'.format(filed.id)])]
    assert [(n['name'], n['keys']) for n in tree[0]['children']] == [('Day 2', ['quiz:{}'.format(filed.id)])]
    ids = re.findall(r'\sid="([^"]+)"', page)
    assert len(ids) == len(set(ids))
    for url in ('/quiz/results?folder=all', '/userdet?folder=all', '/quiz/listuser?folder=all', '/quiz/archive?folder=all', '/quiz/listvp?folder=all'):
        page = teach.get(url).data.decode()
        ids = re.findall(r'\sid="([^"]+)"', page)
        assert len(ids) == len(set(ids)), (url, [i for i in ids if ids.count(i) > 1][:3])
