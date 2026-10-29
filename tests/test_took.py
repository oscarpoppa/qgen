"""How long an attempt took, Start to hand-in, time away included, on the teacher's attempt lines and the
student's results page (the owner, 2026-10-28, To do 73)."""
from datetime import datetime, timedelta

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_assign_pages import ids, quiz_of, copies


def test_took_label_words():
    from app.qgen.models import CQuiz
    start = datetime(2026, 10, 28, 9, 0)
    def took(**kw):
        return CQuiz(startdate=start, compdate=start + timedelta(**kw)).took_label
    assert took(seconds=40) == 'under 1 min'
    assert took(minutes=12, seconds=30) == '12 min'
    assert took(hours=1) == '1 h' and took(hours=1, minutes=5) == '1 h 5 min'
    assert took(days=1) == '1 day' and took(days=2, hours=3, minutes=10) == '2 days 3 h'
    assert CQuiz(startdate=start).took_label is None and CQuiz(compdate=start).took_label is None


def test_took_shows_on_attempt_lines_and_results(app_db):
    from app.qgen.models import CQuiz
    app, db = app_db
    teacher = login(app, 'teach')
    vq, _probs = quiz_of(teacher, 'T1')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    cq = copies(vq)[0]
    start = datetime.now() - timedelta(minutes=30)
    cq.startdate, cq.compdate, cq.completed, cq.score = start, start + timedelta(minutes=12, seconds=30), True, 100.0
    db.session.commit()
    history = teacher.get('/quiz/listuser/{}'.format(ids('sam'))).data.decode()
    assert 'title="How long it took, from Start to hand-in">12 min</span>' in history
    results = teacher.get('/quiz/results/{}'.format(vq.id)).data.decode()
    assert 'title="How long it took, from Start to hand-in">12 min</span>' in results
    assert db.session.get(CQuiz, cq.id).took_label == '12 min'
