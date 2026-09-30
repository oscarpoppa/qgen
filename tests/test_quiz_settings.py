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
    assert 'Your score: 25%' in page and '★ 50%' in page and 'Attempt 2' not in page
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


def test_date_fields_get_the_calendar_control(app_db):
    app, db = app_db
    page = login(app, 'teach').get('/quiz/assign').data.decode()
    # the calendar script is on every page and enhances every date field
    assert 'js/calendar.js' in page
    assert page.count('type="datetime-local"') == 2


def test_attempts_are_named_by_date():
    from app.qgen.models import CQuiz
    cq = CQuiz(create_date=datetime(2026, 9, 3, 8, 0))
    assert cq.when_label == 'assigned Sep 3'
    cq.startdate = datetime(2026, 9, 4, 13, 5)
    assert cq.when_label == 'started Sep 4'
    cq.compdate, cq.needs_review = datetime(2026, 9, 4, 13, 45), True
    assert cq.when_label == 'Sep 4, 1:45 PM'
    cq.needs_review, cq.completed, cq.compdate = False, True, datetime(2026, 9, 4, 0, 7)
    assert cq.when_label == 'Sep 4, 12:07 AM'


def test_release_answers_to_one_student(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    from app.messages.models import Message
    ids = {u.username: u.id for u in User.query.filter_by(is_admin=False)}
    teacher = login(app, 'teach')
    f = problem_form('numeric', 'N', '[a] + 1', 'a + 1', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}])
    teacher.post('/quiz/makevprob', data=f)
    teacher.post('/quiz/makevquiz', data={'title': 'Hidden', 'vplist': str(VProblem.query.one().id), 'hide_answers': 'y'})
    vq = VQuiz.query.one()
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids['sam'], ids['kim']]})
    for name in ('sam', 'kim'):
        with app.test_request_context():
            S.submit(CQuiz.query.filter_by(assignee=ids[name]).one(), {1: '999'})  # wrong
    sam_cq = CQuiz.query.filter_by(assignee=ids['sam']).one()
    kim_cq = CQuiz.query.filter_by(assignee=ids['kim']).one()
    sam, kim = login(app, 'sam'), login(app, 'kim')
    shown = lambda client, cq: '<dt>Correct answer</dt>' in client.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert not shown(sam, sam_cq) and not shown(kim, kim_cq)

    # Results by student offers it per student
    page = teacher.get('/quiz/listuser').data.decode()
    assert page.count('/quiz/releasecq/') == 2 and 'Answers hidden' in page
    # release to sam only: sam sees the answers (and gets a notice), kim still doesn't
    teacher.post('/quiz/releasecq/{}'.format(sam_cq.id))
    db.session.expire_all()
    assert shown(sam, sam_cq) and not shown(kim, kim_cq)
    assert 'correct answers for &#34;Hidden&#34;' in sam.get('/messages/notices').data.decode()
    assert 'correct answers' not in kim.get('/messages/notices').data.decode()
    assert 'answers released' in teacher.get('/quiz/listuser').data.decode()
    # the API agrees
    from test_api import Api
    body = Api(app, 'sam').get('/my/attempts/{}/results'.format(sam_cq.id)).get_json()
    assert body['answers_shown'] is True and 'correct_answer' in body['items'][0]
    body = Api(app, 'kim').get('/my/attempts/{}/results'.format(kim_cq.id)).get_json()
    assert body['answers_shown'] is False and 'correct_answer' not in body['items'][0]
    # a retake keeps it released for sam
    teacher.post('/quiz/retcq/{}'.format(sam_cq.id))
    db.session.expire_all()
    new = CQuiz.query.filter_by(assignee=ids['sam']).order_by(CQuiz.id.desc()).first()
    assert new.id != sam_cq.id and new.answers_released
    # hide again: back to hidden for sam
    teacher.post('/quiz/releasecq/{}'.format(sam_cq.id))
    db.session.expire_all()
    assert not shown(sam, sam_cq)
    assert not any(c.answers_released for c in CQuiz.query.filter_by(assignee=ids['sam']))
    # releasing the whole quiz still works for everyone
    teacher.post('/quiz/releasevq/{}'.format(vq.id))
    db.session.expire_all()
    assert shown(sam, sam_cq) and shown(kim, kim_cq)
    assert 'Answers released to everyone' in teacher.get('/quiz/listuser').data.decode()
    # students can't release answers to themselves
    assert sam.post('/quiz/releasecq/{}'.format(kim_cq.id)).status_code == 302
    db.session.expire_all()
    assert not CQuiz.query.get(kim_cq.id).answers_released


def test_correct_answer_shown_under_right_answers_too(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Easy', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    with app.test_request_context():
        S.submit(cq, {1: '4'})
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert cq.score == 100 and '<dt>Correct answer</dt><dd>4</dd>' in page


def test_question_type_is_fixed_once_students_have_it(app_db):
    # results pages, grading and details all read answers as the problem's type
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    vp = VProblem.query.one()
    # not given to anyone yet: the type can still change
    assert teacher.post('/quiz/editvprob/{}'.format(vp.id), data=problem_form('text', 'N', 'Say four', 'four', [])).status_code == 302
    db.session.expire_all()
    assert VProblem.query.one().qtype == 'text'
    teacher.post('/quiz/editvprob/{}'.format(vp.id), data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Q', 'vplist': str(vp.id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    with app.test_request_context():
        S.submit(cq, {1: '4'})
    # given to a student: changing the type is refused, other edits still work
    r = teacher.post('/quiz/editvprob/{}'.format(vp.id), data=problem_form('text', 'N', 'Say four', 'four', []))
    assert r.status_code == 200 and 'its question type can' in r.data.decode()
    db.session.expire_all()
    assert VProblem.query.one().qtype == 'numeric'
    assert teacher.post('/quiz/editvprob/{}'.format(vp.id), data=problem_form('numeric', 'N2', 'What is 2 + 2?', '4', [])).status_code == 302
    assert '<dt>Correct answer</dt><dd>4</dd>' in login(app, 'sam').get('/quiz/take/{}'.format(cq.id)).data.decode()


def test_folded_quiz_box_knows_what_it_holds(app_db):
    # each box carries its attempts and their state, so a folded box can flag a change
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Fold', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    before = sam.get('/mypage').data.decode()
    assert 'data-attempts="{}"'.format(cq.id) in before and 'data-sig="{}|new|None"'.format(cq.id) in before
    assert 'class="badge badge-warn quiz-flag" hidden' in before
    with app.test_request_context():
        S.submit(cq, {1: '4'})
        new = S.retake(cq)
    after = sam.get('/mypage').data.decode()
    assert 'data-attempts="{},{}"'.format(cq.id, new.id) in after or 'data-attempts="{},{}"'.format(new.id, cq.id) in after
