"""A student's Home: counts of what's waiting, what's due soon, and the awards they earn."""
import re
from datetime import datetime, timedelta

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_archive import ids
from test_dashboard import make_quiz, give


def finish(cq, score, when):
    from app import db
    cq.startdate, cq.compdate, cq.completed, cq.score = when - timedelta(minutes=5), when, True, score
    db.session.commit()
    return cq


def titles(page):
    """The awards earned (not the ones still to earn) on a page."""
    part = page.split('Still to earn')[0]
    return re.findall(r'<li class="award award-\w+">.*?<strong>([^<]+)</strong>', part, re.S)


def test_students_land_on_home_with_their_counts(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    now = datetime.now()
    q1, q2, q3, q4 = (make_quiz(app, teach, t) for t in ('Q1', 'Q2', 'Q3', 'Q4'))
    give(q1, 'sam')                                      # to do
    give(q2, 'sam', closes_at=now + timedelta(days=1))   # to do, due soon
    started = give(q3, 'sam', closes_at=now + timedelta(days=30))
    started.startdate = now
    db.session.commit()                                  # in progress, not due soon
    finish(give(q4, 'sam'), 80, now)                     # done: not counted
    page = sam.get('/home').data.decode()
    counts = dict((label, int(n)) for n, label in re.findall(r'<span class="dash-num">(\d+)</span><span>([^<]+)</span>', page))
    assert counts == {'new': 2, 'in progress': 1, 'due within 2 days': 1}
    # waiting: due soonest first, each with its button
    waiting = page.split('class="box-title">Waiting for you</h2>')[1].split('</details>')[0]
    assert re.findall(r'<strong>“([^”]+)”</strong>', waiting) == ['Q2', 'Q3', 'Q1']
    assert '>Continue</a>' in page and page.count('>Start</a>') == 2
    assert '<a href="/home" class="active" aria-current="page">Home</a>' in page  # in the menu for students
    # the boxes fold away (remembered in the browser)
    assert 'data-box="waiting" open>' in page and 'data-box="awards" open>' in page
    # teachers have Home too (they take quizzes as students do); they still land on the Dashboard
    assert '<a href="/home">Home</a>' in teach.get('/dashboard').data.decode()
    assert teach.get('/home').status_code == 200


def test_awards(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    t = datetime(2026, 9, 1, 10, 0)
    quizzes = [make_quiz(app, teach, 'W{}'.format(i)) for i in range(6)]
    assert titles(sam.get('/home').data.decode()) == []
    page = sam.get('/home').data.decode()
    assert 'Finish quizzes to earn awards.' in page and 'Finish your first quiz' in page
    finish(give(quizzes[0], 'sam'), 50, t)                                  # first quiz
    finish(give(quizzes[0], 'sam'), 75, t + timedelta(days=1))              # retake +25: comeback
    finish(give(quizzes[1], 'sam'), 100, t + timedelta(days=2))             # perfect; streak 1
    finish(give(quizzes[2], 'sam'), 95, t + timedelta(days=3))              # streak 2
    finish(give(quizzes[3], 'sam'), 92, t + timedelta(days=4))              # streak 3
    finish(give(quizzes[4], 'sam'), 100, t + timedelta(days=5))             # perfect; 5 quizzes; streak 4
    page = sam.get('/home').data.decode()
    assert titles(page) == ['Perfect score', '5 quizzes', '3 in a row', 'Perfect score', 'Comeback', 'First quiz']
    assert '100% on &#34;W4&#34;' in page or '100% on "W4"' in page
    assert 'Up 25 points on' in page
    # still to earn: the next of each kind only
    rest = page.split('Still to earn')[1]
    assert '10 quizzes' in rest and '5 in a row' in rest and 'Perfect score' not in rest and 'Comeback' not in rest
    # a regrade is reflected: no perfect score on W1 any more
    from app.qgen.models import CQuiz
    cq = CQuiz.query.filter_by(vquiz_id=quizzes[1].id).one()
    cq.score = 90
    db.session.commit()
    assert titles(sam.get('/home').data.decode()).count('Perfect score') == 1
    # attempts being graded don't count
    being = give(quizzes[5], 'sam')
    being.needs_review, being.compdate = True, t + timedelta(days=6)
    db.session.commit()
    assert '6 quizzes' not in sam.get('/home').data.decode()
    # teachers see them on the student's page; other students never do
    page = teach.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert 'class="box-title">Awards</span><span class="badge box-count">5 awards</span>' in page
    kim = login(app, 'kim')
    assert titles(kim.get('/home').data.decode()) == []
    assert kim.get('/quiz/listuser/{}'.format(ids('sam'))).status_code == 302


def test_a_perfect_score_means_the_score_that_counts(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    t = datetime(2026, 9, 1, 10, 0)
    avg, best, latest = (make_quiz(app, teach, n) for n in ('Avg', 'Best', 'Latest'))
    for vq, rule in ((avg, 'average'), (best, 'best'), (latest, 'latest')):
        vq.retake_rule = rule
    db.session.commit()
    # average: 50 then 100 counts as 75, so no award; a third 100 isn't enough either
    finish(give(avg, 'sam'), 50, t)
    finish(give(avg, 'sam'), 100, t + timedelta(hours=1))
    # best: a 100% retake counts
    finish(give(best, 'sam'), 60, t + timedelta(hours=2))
    finish(give(best, 'sam'), 100, t + timedelta(hours=3))
    # latest: 100 then 80 counts as 80, so no award
    finish(give(latest, 'sam'), 100, t + timedelta(hours=4))
    finish(give(latest, 'sam'), 80, t + timedelta(hours=5))
    page = sam.get('/home').data.decode()
    perfect = re.findall(r'100% on (?:&#34;|")([^"&]+)', page.split('Still to earn')[0])
    assert perfect == ['Best']
    # a teacher's own rule for this student changes it: "best" on Latest makes it count
    from app.qgen.models import CQuiz
    from app.qgen import services as S
    S.set_retake_rule(CQuiz.query.filter_by(vquiz_id=latest.id).order_by(CQuiz.id.desc()).first(), 'best')
    page = sam.get('/home').data.decode()
    assert sorted(re.findall(r'100% on (?:&#34;|")([^"&]+)', page.split('Still to earn')[0])) == ['Best', 'Latest']


def test_recently_completed(app_db):
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    now = datetime.now()
    quizzes = [make_quiz(app, teach, 'R{}'.format(i)) for i in range(13)]
    page = sam.get('/home').data.decode()
    assert 'class="box-title">Recently completed</h2><span class="badge box-count">0 quizzes</span>' in page and 'Nothing handed in during the last 14 days.' in page
    finish(give(quizzes[0], 'sam'), 40, now - timedelta(days=20))       # too long ago
    finish(give(quizzes[1], 'sam'), 85, now - timedelta(days=3))
    being = give(quizzes[2], 'sam')                                       # being graded
    being.needs_review, being.startdate, being.compdate = True, now - timedelta(hours=2), now - timedelta(hours=1)
    db.session.commit()
    give(quizzes[3], 'sam')                                               # not handed in
    page = sam.get('/home').data.decode()
    part = page.split('class="box-title">Recently completed</h2>')[1].split('</details>')[0]
    assert re.findall(r'<strong>“([^”]+)”</strong>', part) == ['R2', 'R1']  # newest first
    assert 'Teacher is checking' in part and '>85%</span>' in part and '>View</a>' in part and '>Results</a>' in part
    # at most 10
    for i in range(4, 13):
        finish(give(quizzes[i], 'sam'), 90, now - timedelta(minutes=i))
    part = sam.get('/home').data.decode().split('class="box-title">Recently completed</h2>')[1].split('</details>')[0]
    assert len(re.findall(r'<strong>“', part)) == 10


def test_home_follows_hand_ins(app_db):
    # an open Home reloads itself when a quiz is handed in or graded (its watch key, "mine")
    app, db = app_db
    teach, sam = login(app, 'teach'), login(app, 'sam')
    cq = give(make_quiz(app, teach, 'Live'), 'sam')
    page = sam.get('/home').data.decode()
    key, drawn = re.search(r'data-watch="([^"]+)" data-watch-state="([^"]+)"', page).groups()
    assert key == 'home' and sam.get('/messages/poll?watch=home').get_json()['watch'] == drawn
    finish(cq, 90, datetime.now())
    assert sam.get('/messages/poll?watch=home').get_json()['watch'] != drawn


def test_box_grids_are_packed_on_every_page(app_db):
    """Every page loads the script that lets grid boxes take only the height they need (so a
    short box doesn't leave a hole under it), and it covers Home's and the Dashboard's grids."""
    import os
    app, db = app_db
    from test_flow import login
    home = login(app, 'sam').get('/home').data.decode()
    assert 'js/masonry.js' in home and 'class="dash-grid"' in home
    js = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'masonry.js')).read()
    assert "'.dash-grid, .grid'" in js


def test_every_box_opens_and_is_remembered_the_same_way(app_db):
    """One script for every box (static/js/boxes.js): loaded right after the page, for this
    person; page sections drawn open, list boxes marked data-list, no other memory left; and
    scroll areas let the mouse wheel go on to the page."""
    import os
    app, db = app_db
    from test_flow import login
    page = login(app, 'sam').get('/home').data.decode()
    sam_id = __import__('app.user.models', fromlist=['User']).User.query.filter_by(username='sam').one().id
    assert 'js/boxes.js?v=' in page and 'data-user="{}"'.format(sam_id) in page
    assert page.index('js/boxes.js') < page.index('</main>') + 400 and 'qgen-home-closed' not in page
    assert 'data-box="waiting" open>' in page
    here = os.path.join(os.path.dirname(__file__), '..')
    css = open(os.path.join(here, 'static', 'css', 'app.css')).read()
    assert 'overscroll-behavior' not in css
    for js in ('dashboard.js', 'subjects.js', 'folders.js'):
        text = open(os.path.join(here, 'static', 'js', js)).read()
        assert 'localStorage.setItem(KEY' not in text and 'data-dash-boxes' not in text and 'itemKey' not in text


def test_buttons_that_reload_the_page_keep_your_place(app_db):
    """Every page notes where it was scrolled when a form is sent and puts it back if the same
    page comes back (static/js/place.js); handing in, starting a quiz and the editors don't."""
    import os
    app, db = app_db
    from test_flow import login
    assert 'js/place.js' in login(app, 'sam').get('/home').data.decode()
    here = os.path.join(os.path.dirname(__file__), '..', 'app', 'qgen', 'templates')
    for name in ('quiz_take.html', 'quiz_start.html', 'problem_form.html', 'quiz_form.html', 'assign.html'):
        assert 'data-fresh-page' in open(os.path.join(here, name)).read(), name


def test_sideways_dividers_for_the_folder_list_and_the_side_panel(app_db):
    """static/js/splitter.js on every page: a divider between a folder page's folder list and
    its list, and on the Notices / Messages panel's left edge; the folder layout leaves it a
    column whose width the divider sets."""
    import os
    app, db = app_db
    from test_flow import login
    assert 'js/splitter.js' in login(app, 'teach').get('/quiz/listvq').data.decode()
    here = os.path.join(os.path.dirname(__file__), '..', 'static')
    js = open(os.path.join(here, 'js', 'splitter.js')).read()
    css = open(os.path.join(here, 'css', 'app.css')).read()
    assert "'qgen-side-width'" in js and "'qgen-dock-width'" in js and "'--dock-w'" in js
    assert 'grid-template-columns: var(--side-w, minmax(170px, 260px)) 12px minmax(0, 1fr)' in css


def test_quiz_and_problem_pictures_are_scaled_to_fit(app_db):
    """Every quiz or problem picture (class qimg, wherever it shows) keeps its shape and is
    never wider than its column nor taller than about half the window."""
    import os, re
    css = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'css', 'app.css')).read()
    rule = re.search(r'img\.qimg \{([^}]*)\}', css).group(1)
    assert 'max-height: min(360px, 50vh)' in rule and 'max-width: min(100%, 520px)' in rule
    assert 'width: auto' in rule and 'height: auto' in rule and 'object-fit: contain' in rule
    assert '.question .qimg' not in css  # one rule for all of them
