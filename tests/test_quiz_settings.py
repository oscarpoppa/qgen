"""Autosave, open/close windows, time limits, hidden answers, retake scoring, site settings."""
import json
from datetime import datetime, timedelta

import pytest

from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)


def make_quiz(app, db, teacher, **quiz):
    from app.qgen.models import VProblem, VQuiz
    f1 = problem_form('numeric', 'Add', '[a] + 1 = ?', 'a + 1', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}])
    f2 = problem_form('choice_many', 'Evens', 'Which are even?', '', [], choices='*2\n*4\n3')
    for f in (f1, f2):
        assert teacher.post('/quiz/makevprob', data=f).status_code == 302
    ids = ', '.join(str(p.id) for p in VProblem.query.order_by(VProblem.id))
    data = dict({'title': 'Settings quiz', 'vplist': ids, 'shuffle_order': 'y', 'retake_rule': 'best'}, **quiz)
    assert teacher.post('/quiz/makevquiz', data=data).status_code == 302
    return VQuiz.query.filter_by(title='Settings quiz').one()


def assign(teacher, vq, users, **when):
    data = dict({'vquiz': vq.id, 'users': [u.id for u in users]}, **when)
    r = teacher.post('/quiz/assign', data=data)
    assert r.status_code == 302, r.data.decode()[:600]


def student(db, name):
    from app.user.models import User
    return User.query.filter_by(username=name).one()


def test_autosave_prefill_and_time_limit(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    sam_u = student(db, 'sam')
    assign(teacher, vq, [sam_u], time_limit='30')
    cq = CQuiz.query.filter_by(assignee=sam_u.id).one()
    sam = login(app, 'sam')
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'data-remaining="' in page and 'id="timer"' in page
    num = [cp for cp in cq.cproblems if cp.vproblem.qtype == 'numeric'][0]
    many = [cp for cp in cq.cproblems if cp.vproblem.qtype == 'choice_many'][0]
    right = [str(i) for i in many.conc_opts['correct']]
    r = sam.post('/quiz/take/{}/save'.format(cq.id), data={
        'Number{}'.format(num.ordinal): num.conc_ansr, 'Number{}'.format(many.ordinal): right,
        'Number{}_present'.format(many.ordinal): '1'})
    assert r.get_json()['ok']
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'value="{}"'.format(num.conc_ansr) in page and page.count('checked') >= len(right)
    # someone else can't save into sam's quiz
    kim = login(app, 'kim')
    assert kim.post('/quiz/take/{}/save'.format(cq.id), data={}).status_code == 403
    # time runs out: the saved answers are handed in on the next visit
    cq.startdate = datetime.now() - timedelta(minutes=45)
    db.session.commit()
    sam.get('/quiz/take/{}'.format(cq.id))
    db.session.expire_all()
    cq = db.session.get(CQuiz, cq.id)
    assert cq.completed and cq.score == 100
    assert not sam.post('/quiz/take/{}/save'.format(cq.id), data={}).get_json()['ok']


def test_open_and_close_window(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    fmt = '%Y-%m-%dT%H:%M'
    later = datetime.now() + timedelta(days=1)
    r = teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [student(db, 'sam').id],
                                            'opens_at': later.strftime(fmt), 'closes_at': (later - timedelta(hours=1)).strftime(fmt)})
    assert b'closing time must be after' in r.data
    assign(teacher, vq, [student(db, 'sam')], opens_at=later.strftime(fmt), closes_at=(later + timedelta(hours=1)).strftime(fmt))
    cq = CQuiz.query.one()
    sam = login(app, 'sam')
    assert b'This quiz opens' in sam.get('/quiz/take/{}'.format(cq.id)).data
    assert b'Opens ' in sam.get('/mypage').data
    db.session.expire_all()
    assert db.session.get(CQuiz, cq.id).startdate is None  # peeking early doesn't start the clock
    cq.opens_at, cq.closes_at = datetime.now() - timedelta(hours=2), datetime.now() - timedelta(hours=1)
    db.session.commit()
    sam.get('/quiz/take/{}'.format(cq.id))
    db.session.expire_all()
    assert db.session.get(CQuiz, cq.id).completed


def test_hidden_answers_and_release(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, VQuiz
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher, hide_answers='y')
    assign(teacher, vq, [student(db, 'sam')])
    cq = CQuiz.query.one()
    sam = login(app, 'sam')
    sam.post('/quiz/take/{}'.format(cq.id), data={})  # all blank -> all wrong
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'Correct answer' not in page and 'show the correct answers later' in page and '0%' in page
    assert 'Correct answer' in teacher.get('/quiz/take/{}'.format(cq.id)).data.decode()  # teacher always sees them
    teacher.post('/quiz/releasevq/{}'.format(vq.id))
    assert 'Correct answer' in sam.get('/quiz/take/{}'.format(cq.id)).data.decode()


def test_retake_scoring_rules(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz, VQuiz, combined_score
    assert combined_score('best', [40, 90, 70]) == 90
    assert combined_score('latest', [40, 90, 70]) == 70
    assert combined_score('first', [40, 90, 70]) == 40
    assert abs(combined_score('average', [40, 90, 70]) - 200 / 3) < 1e-9
    assert combined_score('best2', [40, 90, 70]) == 80
    assert combined_score('best', []) is None
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher, retake_rule='average')
    sam_u = student(db, 'sam')
    assign(teacher, vq, [sam_u])
    sam = login(app, 'sam')
    first = CQuiz.query.one()
    num = [cp for cp in first.cproblems if cp.vproblem.qtype == 'numeric'][0]
    sam.post('/quiz/take/{}'.format(first.id), data={'Number{}'.format(num.ordinal): num.conc_ansr})  # 50%
    teacher.post('/quiz/retcq/{}'.format(first.id))
    second = CQuiz.query.filter(CQuiz.id != first.id).one()
    sam.post('/quiz/take/{}'.format(second.id), data={})  # 0%
    page = sam.get('/mypage').data.decode()
    assert 'Your score: 25%' in page and '★ 50%' in page and 'Attempt 2' in page
    # the teacher counts only sam's best attempt
    r = teacher.post('/quiz/retakerule/{}'.format(second.id), data={'rule': 'best'})
    assert r.status_code == 302
    assert 'Your score: 50%' in sam.get('/mypage').data.decode()
    ulist = teacher.get('/quiz/listuser').data.decode()
    assert 'selected>The best attempt' in ulist.replace('"selected" ', 'selected').replace('selected ', 'selected') or 'The best attempt' in ulist
    teacher.post('/quiz/retakerule/{}'.format(second.id), data={'rule': ''})
    assert 'Your score: 25%' in sam.get('/mypage').data.decode()


def test_site_settings_logo_and_name(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    r = teacher.post('/settings', data={'site_name': 'Lincoln Middle School', 'logo': 'crest.png', 'code': 'maple-7'})
    assert r.status_code == 302
    page = login(app, 'sam').get('/mypage').data.decode()
    assert 'Lincoln Middle School' in page and 'crest.png' in page and 'class="brand-logo"' in page
    assert login(app, 'sam').get('/settings').status_code == 302  # students can't change settings
