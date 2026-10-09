"""The review pass: only this site's pages after signing in or an action, pages that keep
up (and stay quick), Back buttons that go where you came from, the grading queue, what a
student is offered after handing in, nicknames, and wording a young student understands."""
import re
from datetime import datetime, timedelta

from sqlalchemy import event

from test_flow import app_db, login, take_page, no_titles  # noqa: F401  (fixture)
from test_dashboard import make_quiz, give
from test_archive import ids


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
    assert '<a class="btn btn-secondary" href="/dashboard" data-back>← Dashboard</a>' in no_titles(page)
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert '<a class="btn btn-secondary" href="/userdet" data-back>← Users</a>' in no_titles(page)
    # from another site, or from the page itself: its own Back
    for ref in ('https://evil.example/dashboard', 'http://localhost/quiz/listuser/{}'.format(ids('sam'))):
        page = teach.get('/quiz/listuser/{}'.format(ids('sam')), headers={'Referer': ref}).data.decode()
        assert '← Users</a>' in page, ref
    # and a student page names the student
    page = teach.get('/quiz/results', headers={'Referer': 'http://localhost/quiz/listuser/{}'.format(ids('sam'))}).data.decode()
    assert "← sam&#39;s student page</a>" in page


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


def test_after_handing_in_the_student_is_offered_the_next_quiz(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    a, b = make_quiz(app, teach, 'A'), make_quiz(app, teach, 'B essay', essay=True)
    done = give(b, 'sam')
    nxt = give(a, 'sam')
    from app.qgen import services as S
    S.submit(done, {1: 'Light makes sugar.'})
    page = sam.get('/quiz/take/{}'.format(done.id)).data.decode()
    assert 'Handed in!' in page and 'Your teacher is checking' in page
    assert '<a class="btn" href="/quiz/take/{}">Next: “A” →</a>'.format(nxt.id) in no_titles(page)
    assert '← Home</a>' in page
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
    assert 'Hi, sam (Sammy the Great)!' in sam.get('/home').data.decode()
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
        assert '📥</span> Not in a folder' in page and '🗂️</span> All' in page and '+ New folder' in page, url
        assert 'data-fold-key="' in page and 'Expand all' in page, url
    # one name for "in no folder" everywhere on screen
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app')
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith('.html'):
                text = open(os.path.join(folder, name)).read()
                for old in ('Unsorted', 'Main list', 'Top level', 'No folder'):
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
    # no folder chosen: the Helper doesn't ask for one, and it saves into Not in a folder
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
    assert '<a href="/quiz/take/{}" title="sam'.format(cq.id) in box and 's copy of this quiz">“Week 1”</a>' in box
    assert '/quiz/results/{}'.format(vq.id) not in box
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
    # Math holds A and (in Fractions) B; C is in no folder; a folder with none of sam's quizzes isn't shown
    math_box = page[page.index('data-folder-box="{}"'.format(math.id)):page.index('data-folder-box="none"')]
    assert '>A</span>' in math_box and 'data-folder-box="{}"'.format(frac.id) in math_box and '>B</span>' in math_box
    empty = VQGroup.query.filter_by(title='Empty one').one()
    assert '>C</span>' in page[page.index('data-folder-box="none"'):] and 'data-folder-box="{}"'.format(empty.id) not in page
    # no quiz folders at all: the quizzes are listed as before
    kim_q = give(c, 'kim')
    page = teach.get('/quiz/listuser/{}'.format(ids('kim'))).data.decode()
    assert not re.search(r'data-folder-box="(?!new")', page) and '>C</span>' in page  # only the automatic New box


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
    assert 'average 0%' in results
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


# ---------------------------------------------------------------- pages remember where you were

def test_folder_pages_remember_the_folder_you_were_in(app_db):
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
    # the first time: the page's own default (quizzes in no folder)
    assert shown(sam.get('/mypage').data.decode()) == 'main'
    # open the folder, go Home, come back from the menu: still in the folder
    sam.get('/mypage?folder={}'.format(folder.id))
    sam.get('/home')
    page = sam.get('/mypage').data.decode()
    assert shown(page) == str(folder.id) and '>A</h2>' in page and '>B</h2>' not in page
    # the side list's links say which folder, so "Not in a folder" and "All" can be picked again
    assert 'href="/mypage?folder=main"' in page and 'href="/mypage?folder=all"' in page
    sam.get('/mypage?folder=all')
    assert shown(sam.get('/mypage').data.decode()) == 'all'
    # a folder that's gone: the default again
    sam.get('/mypage?folder={}'.format(folder.id))
    sam.post('/mypage/folders/{}/delete'.format(folder.id))
    assert shown(sam.get('/mypage').data.decode()) == 'main'
    # each page remembers its own; another person's choice is theirs
    teach.get('/quiz/listvq?folder=main')
    assert shown(teach.get('/quiz/listvq').data.decode()) == 'main'
    assert shown(teach.get('/quiz/archive').data.decode()) == 'all'
    assert shown(login(app, 'teach').get('/quiz/listvq').data.decode()) == 'all'


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
    # each counter opens My quizzes' own folder of the same name
    assert 'href="/mypage?folder=new"' in home and 'href="/mypage?folder=started"' in home
    assert 'href="/mypage?folder=soon"' in home
    due = sam.get('/mypage?folder=soon').data.decode()
    assert re.findall(r'<h2 title="([^"]+)" class="box-title">', due) == ['Soon']
    assert '⏰</span> Due within 2 days</a>' in due and '>1 due</span>' in due and 'hand these in soon' in due
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
    # it doesn't change the folder My quizzes remembers
    sam.get('/mypage?folder=main')
    sam.get('/mypage?show=todo')
    assert 'data-view="main"' in sam.get('/mypage').data.decode()


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
        assert re.search(r'<a class="btn btn-secondary" href="[^"]+" data-back>← ', no_titles(page)), url
    # with nowhere better known, My profile goes back to Home (Dashboard for a teacher)
    assert 'href="/home" data-back>← Home</a>' in no_titles(sam.get('/profile').data.decode())
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
    # back to the list: the list with the quiz lit up
    r = teach.post('/quiz/editvquiz/{}'.format(vq.id), data=dict(form, next='/quiz/listvq?folder=all'))
    assert r.headers['Location'].endswith('/quiz/listvq?show={}'.format(vq.id))


def test_home_counter_views_say_what_they_show(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    give(make_quiz(app, teach, 'New one'), 'sam')
    page = sam.get('/mypage?show=todo').data.decode()
    assert '<h2 id="folder-title" class="folder-title">📝 To do: quizzes you haven’t started</h2>' in page
    page = sam.get('/mypage?show=started').data.decode()
    assert '✏️ Started: quizzes you haven’t handed in</h2>' in page
    assert 'You have no quizzes started and not handed in. 🎉' in page
    page = sam.get('/mypage?show=soon').data.decode()
    with app.app_context():
        from app import tuning
        days = tuning.get('due_soon_days')
    within = '{} day{}'.format(days, '' if days == 1 else 's')
    assert '⏰ Due within {}</h2>'.format(within) in page and 'Nothing is due within {}. 🎉'.format(within) in page
    # the ordinary page keeps its own heading
    assert 'class="folder-title">All quizzes</h2>' in sam.get('/mypage?folder=all').data.decode()


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
    assert 'Removed quizzes (' not in teach.get('/quiz/listvq').data.decode()
    # never assigned: deleted for good, as before
    other = make_quiz(app, teach, 'Unused')
    teach.post('/quiz/delvq/{}'.format(other.id))
    assert db.session.get(VQuiz, other.id) is None


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
    assert 'Archive all 2 attempts' in page and 'Take away' not in page
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
    # and Not in a folder has the started one
    assert '<span class="side-dot dot-started" title="1 attempt in progress" role="img" aria-label="1 attempt in progress">1</span>' in page
    # only the automatic folders carry full badges; the others have dots
    assert 'side-flag"' not in page
    page = sam.get('/mypage?folder=new').data.decode()
    assert re.findall(r'<h2 title="([^"]+)" class="box-title">', page) == ['Fresh']
    assert '🆕 New: quizzes you haven’t started</h2>' in page and '📁 Math</a>' in page  # its folder too
    # still in its own folder
    assert 'Fresh' in sam.get('/mypage?folder={}'.format(folder.id)).data.decode()
    # the teacher's student page: a New box with the same quiz and a badge
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    box = page.split('data-folder-box="new"')[1].split('        </div>\n      </details>')[0]
    assert '1 new</span>' in box and 'Fresh' in box and 'Begun' not in box and 'Done' not in box
    # started: no longer new, no badge
    for c in fresh.cquizzes:
        c.startdate = datetime.now()
    db.session.commit()
    mine = sam.get('/mypage').data.decode()
    assert ' new</span>' not in mine.split('<nav aria-label="Folders">')[1].split('</nav>')[0] and '2 started</span>' in mine
    assert 'No new quizzes right now. 🎉' in sam.get('/mypage?folder=new').data.decode()
    assert 'nothing new</span>' in teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()


def test_a_teacher_taking_a_quiz_gets_the_students_pages(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.qgen import services as S
    vq = make_quiz(app, teach, 'Mine')
    cq = give(vq, 'teach')
    home = teach.get('/home').data.decode()
    assert '“Mine”' in home and 'href="/mypage?folder=new"' in home and 'href="/mypage?folder=started"' in home
    page = teach.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'href="/home" data-back>← Home</a>' in no_titles(page)
    S.submit(cq, {1: '4'})
    page = teach.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'href="/home" data-back>← Home</a>' in no_titles(page) and 'Answer key' not in no_titles(page)
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
    assert '1 quiz is deleted for good.' in page and '1 quiz is taken off the Quizzes page; students keep their copies' in page
    r = teach.post('/quiz/subjects/quizzes/{}/purge'.format(term.id), follow_redirects=True).data.decode()
    assert '1 quiz deleted. 1 quiz removed (students keep their copies).' in r
    assert db.session.get(VQuiz, spare.id) is None and db.session.get(VQuiz, used.id).removed_at is not None


def test_dashboard_recent_hand_ins_name_the_quiz_without_a_link(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.qgen import services as S
    vq = make_quiz(app, teach, 'Handed')
    cq = give(vq, 'sam')
    S.submit(cq, {1: '4'})
    page = teach.get('/dashboard').data.decode()
    row = page.split('/quiz/take/{}'.format(cq.id))[0].rsplit('<li>', 1)[1]
    assert '<span>“Handed”</span>' in row and "This quiz's results" not in row


def test_dashboard_waiting_for_grading_names_the_quiz_without_a_link(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    from app.qgen.models import CQuiz
    vq = make_quiz(app, teach, 'Essay week')
    cq = give(vq, 'sam')
    cq.needs_review, cq.compdate = True, datetime.now()
    db.session.commit()
    page = teach.get('/dashboard').data.decode()
    row = page.split('/quiz/review/{}'.format(cq.id))[0].rsplit('<li>', 1)[1]
    assert '<span>“Essay week”</span>' in row and "This quiz's results" not in row


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
    """Every quiz on My quizzes has "📁 ▾" in its heading (new, started or done), whose list
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
    assert 'class="move-form move-mini"' in head and 'Not in a folder (here now)' in head
    r = sam.post('/mypage/move', data={'quiz': fresh.id, 'to': wk.id, 'view': 'new', 'from': 'top'}, follow_redirects=True)
    page = r.data.decode()
    assert 'Fresh' in page and '📁 Week 1 (here now)' in page  # still in New, now in Week 1
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
    assert 'Messages between teachers' in page and '← Messages</a>' in page and 'Messages with' not in page


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
    assert "addEventListener('pagehide'" in keep and 'qgenRun' in keep
