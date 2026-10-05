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
    assert counts == {'to do': 2, 'in progress': 1, 'due within 2 days': 1}
    # waiting: due soonest first, each with its button
    assert re.findall(r'<strong>“([^”]+)”</strong>', page) == ['Q2', 'Q3', 'Q1']
    assert '>Continue</a>' in page and page.count('>Start</a>') == 2
    assert '<a href="/home">Home</a>' in page  # in the menu for students
    # the boxes fold away (remembered in the browser)
    assert 'data-box="waiting" open>' in page and 'data-box="awards" open>' in page and 'qgen-home-closed' in page
    assert '<a href="/home">Home</a>' not in teach.get('/dashboard').data.decode()


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
    assert '<span class="box-name">Awards</span><span class="badge badge-ok">5</span>' in page
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
