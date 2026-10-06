"""The review pass: only this site's pages after signing in or an action, pages that keep
up (and stay quick), Back buttons that go where you came from, the grading queue, what a
student is offered after handing in, nicknames, and wording a young student understands."""
import re
from datetime import datetime, timedelta

from sqlalchemy import event

from test_flow import app_db, login  # noqa: F401  (fixture)
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


def test_new_badge_clears_when_the_quiz_is_opened(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    vq = make_quiz(app, teach)
    teach.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    assert sam.get('/messages/poll').get_json()['quizzes'] == 1
    from app.qgen.models import CQuiz
    cq = CQuiz.query.filter_by(assignee=ids('sam')).one()
    sam.get('/quiz/take/{}'.format(cq.id))  # from Home or a notice, not My quizzes
    assert sam.get('/messages/poll').get_json()['quizzes'] == 0


# ---------------------------------------------------------------- finding your way

def test_menu_marks_where_you_are(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    page = teach.get('/quiz/results').data.decode()
    assert 'href="/quiz/results" class="active" aria-current="page">Results by quiz</a>' in page
    assert re.search(r'<summary class="active">Quizzes</summary>', page)
    assert '<a class="skip-link" href="#main">' in page and '<main id="main"' in page


def test_back_goes_where_you_came_from(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    page = teach.get('/quiz/listuser/{}'.format(ids('sam')), headers={'Referer': 'http://localhost/dashboard'}).data.decode()
    assert '<a class="btn btn-secondary" href="/dashboard">← Dashboard</a>' in page
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert '<a class="btn btn-secondary" href="/userdet">← Users</a>' in page
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
    assert '<input type="hidden" name="next" value="/quiz/results/{}">'.format(vq.id) in page
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
    assert 'See the results →' in r.data.decode()


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
    assert '<a class="btn" href="/quiz/take/{}">Next: “A” →</a>'.format(nxt.id) in page
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
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'value="Hand it in"' in page and "Once you hand it in, you can't change your answers." in page
    mine = sam.get('/mypage').data.decode()
    assert '1 try</span>' in mine
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


def test_my_quizzes_to_do_then_done(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    a, b = make_quiz(app, teach, 'A'), make_quiz(app, teach, 'B')
    done, todo = give(a, 'sam'), give(b, 'sam')
    from app.qgen import services as S
    S.submit(done, {1: '4'})
    page = sam.get('/mypage').data.decode()
    assert page.index('>To do <span') < page.index('“B”' if '“B”' in page else '>B</h2>')
    rest = page[page.index('<details class="month-box done-box"'):]
    assert '>A</h2>' in rest and '>B</h2>' not in rest and 'data-remember="done-main"' in rest
