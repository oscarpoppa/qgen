"""Autosave, open/close windows, time limits, hidden answers, retake scoring, site settings."""
import json
from datetime import datetime, timedelta

import pytest

from test_flow import app_db, login, problem_form, take_page  # noqa: F401  (fixture)


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
    page = take_page(sam, cq.id).data.decode()
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
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert "You can't start this quiz yet" in page and 'It opens' in page and 'and closes' in page
    assert 'name="Number1"' not in page  # no questions
    home = sam.get('/mypage').data.decode()
    assert "You can't start this yet. It opens" in home and 'disabled' in home
    assert '>Start</a>' not in home  # no way in
    # handing in or saving answers early is refused too
    sam.post('/quiz/take/{}'.format(cq.id), data={'Number1': '4'})
    assert sam.post('/quiz/take/{}/save'.format(cq.id), data={'Number1': '4'}).status_code == 409
    db.session.expire_all()
    assert db.session.get(CQuiz, cq.id).startdate is None  # peeking early doesn't start the clock
    assert not db.session.get(CQuiz, cq.id).completed and db.session.get(CQuiz, cq.id).cproblems[0].submitted is None
    cq.opens_at, cq.closes_at = datetime.now() - timedelta(hours=2), datetime.now() - timedelta(hours=1)
    db.session.commit()
    sam.get('/quiz/take/{}'.format(cq.id))
    db.session.expire_all()
    assert db.session.get(CQuiz, cq.id).completed




def test_a_time_limit_fits_between_opening_and_closing(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz
    from app.qgen import services as S
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    fmt = '%Y-%m-%dT%H:%M'
    opens = (datetime.now() + timedelta(days=1)).replace(second=0, microsecond=0)
    when = {'opens_at': opens.strftime(fmt), 'closes_at': (opens + timedelta(minutes=30)).strftime(fmt)}
    # 45 minutes in a 30-minute window: refused, said next to the field, nothing assigned
    r = teacher.post('/quiz/assign', data=dict({'vquiz': vq.id, 'users': [student(db, 'sam').id], 'time_limit': '45'}, **when))
    page = r.data.decode()
    assert r.status_code == 200 and 'The time limit (45 minutes) is longer than the time between opening and closing (30 minutes)' in page
    assert CQuiz.query.count() == 0
    # exactly the window, or less: fine
    assign(teacher, vq, [student(db, 'sam')], time_limit='30', **when)
    assign(teacher, vq, [student(db, 'kim')], time_limit='20', **when)
    assert sorted(c.time_limit for c in CQuiz.query.all()) == [20, 30]
    # only a closing time: measured from now (a day and a half hour away: 120 minutes fits);
    # only an opening time: nothing to compare with
    assign(teacher, vq, [student(db, 'sam')], time_limit='120', closes_at=when['closes_at'])
    assign(teacher, vq, [student(db, 'sam')], time_limit='120', opens_at=when['opens_at'])
    assert CQuiz.query.count() == 4
    soon = (datetime.now() + timedelta(minutes=31)).replace(second=0, microsecond=0)
    r = teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [student(db, 'sam').id], 'time_limit': '45',
                                           'closes_at': soon.strftime(fmt)})
    assert 'The time limit (45 minutes) is longer than the time left until the quiz closes (' in r.data.decode()
    assert CQuiz.query.count() == 4
    assert S.time_limit_error(None, soon, 45, now=soon - timedelta(minutes=50)) is None  # measured from now
    assert S.time_limit_error(None, soon - timedelta(days=1), 45) is None  # already closed: not this message
    # the same rule however it's assigned (the app API too)
    try:
        S.assign(vq, [student(db, 'sam')], opens, opens + timedelta(minutes=10), 11)
        assert False, 'too long was accepted'
    except S.ServiceError as exc:
        assert '(11 minutes)' in str(exc) and 'Make it 10 minutes or less' in str(exc)
    from app.api.models import ApiToken
    token = ApiToken.issue(student(db, 'teach'), 't')[1]
    r = app.test_client().post('/api/v2/quizzes/{}/assign'.format(vq.id), headers={'Authorization': 'Bearer ' + token},
                               json={'students': [student(db, 'sam').id], 'opens_at': when['opens_at'],
                                     'closes_at': when['closes_at'], 'time_limit_minutes': 31})
    assert r.status_code == 422 and 'longer than the time between opening and closing' in str(r.get_json())
    assert CQuiz.query.count() == 4
    # the page says the most it can be as the times are typed
    assert 'id="limit-window"' in teacher.get('/quiz/assign').data.decode()


def test_students_are_told_when_a_quiz_opens(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz
    from app.qgen import services as S
    from app.messages.models import Message
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    fmt = '%Y-%m-%dT%H:%M'
    opens = (datetime.now() + timedelta(days=1)).replace(second=0, microsecond=0)
    assign(teacher, vq, [student(db, 'sam')], opens_at=opens.strftime(fmt), closes_at=(opens + timedelta(hours=2)).strftime(fmt))
    assign(teacher, vq, [student(db, 'kim')])  # no start time: nothing to announce later
    later_cq = CQuiz.query.filter_by(assignee=student(db, 'sam').id).one()
    now_cq = CQuiz.query.filter_by(assignee=student(db, 'kim').id).one()
    assert not later_cq.open_notice_sent and now_cq.open_notice_sent
    told = lambda c: Message.query.filter(Message.link == '/quiz/take/{}'.format(c.id), Message.body.like('%is open now%')).all()
    with app.test_request_context():
        assert S.announce_opened(opens - timedelta(minutes=1)) == 0  # not yet
        assert S.announce_opened(opens + timedelta(minutes=1)) == 1
        assert S.announce_opened(opens + timedelta(minutes=2)) == 0  # only once
    notes = told(later_cq)
    assert len(notes) == 1 and not told(now_cq)
    assert notes[0].body.startswith('"Settings quiz" is open now. You can start it. It closes ')
    assert notes[0].from_teacher and notes[0].student_id == later_cq.assignee  # Sam's own notice, unread
    sam = login(app, 'sam')
    assert sam.get('/messages/poll').get_json()['notices'] >= 1
    assert 'is open now' in sam.get('/messages/notices').data.decode()
    assert 'is open now' not in login(app, 'teach').get('/messages/notices').data.decode()
    # a student on the site gets it at their next check-in, together with the page change
    assign(teacher, vq, [student(db, 'sam')], opens_at=opens.strftime(fmt))
    cq = CQuiz.query.filter_by(open_notice_sent=False).one()
    before = sam.get('/messages/poll?watch=mine').get_json()
    cq.opens_at = datetime.now() - timedelta(seconds=5)
    db.session.commit()
    after = sam.get('/messages/poll?watch=mine').get_json()
    assert after['latest_notice'] != before['latest_notice'] and after['watch'] != before['watch']
    assert '"Settings quiz" is open now' in after['notice_preview']['text']
    assert len(told(cq)) == 1
    sam.get('/messages/poll?watch=mine')
    assert len(told(cq)) == 1  # still once
    # a teacher's check-in announces nothing for students
    assign(teacher, vq, [student(db, 'kim')], opens_at=opens.strftime(fmt))
    kims = CQuiz.query.filter_by(open_notice_sent=False).one()
    kims.opens_at = datetime.now() - timedelta(seconds=5)
    db.session.commit()
    teacher.get('/messages/poll')
    assert not told(kims)


def test_no_open_notice_when_it_no_longer_makes_sense(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz
    from app.qgen import services as S
    from app.messages.models import Message
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    fmt = '%Y-%m-%dT%H:%M'
    opens = (datetime.now() + timedelta(days=1)).replace(second=0, microsecond=0)
    assign(teacher, vq, [student(db, 'sam'), student(db, 'kim')], opens_at=opens.strftime(fmt),
           closes_at=(opens + timedelta(hours=1)).strftime(fmt))
    # the server was off the whole time it was open: by now it has closed again
    with app.test_request_context():
        assert S.announce_opened(opens + timedelta(hours=3)) == 0
    assert all(c.open_notice_sent for c in CQuiz.query.all())  # and never later either
    assert not Message.query.filter(Message.body.like('%is open now%')).count()
    # an attempt archived and restored after it opened isn't announced
    assign(teacher, vq, [student(db, 'sam')], opens_at=opens.strftime(fmt))
    cq = CQuiz.query.filter_by(open_notice_sent=False).one()
    with app.test_request_context():
        a = S.archive_attempt(cq)
        db.session.commit()
        restored = S.restore_attempt(a)
    assert not restored.open_notice_sent  # still waiting to open: still to be announced
    restored.opens_at = datetime.now() - timedelta(minutes=5)
    db.session.commit()
    with app.test_request_context():
        a = S.archive_attempt(restored)
        db.session.commit()
        assert S.restore_attempt(a).open_notice_sent


def test_correct_answers_always_show_once_finished(app_db):
    # there's no "hide the answers until I release them" any more
    app, db = app_db
    from app.qgen.models import CQuiz
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    assign(teacher, vq, [student(db, 'sam')])
    cq = CQuiz.query.one()
    sam = login(app, 'sam')
    sam.post('/quiz/take/{}'.format(cq.id), data={})  # all blank -> all wrong
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'Correct answer' in page and 'show the correct answers later' not in page and '0%' in page
    form = teacher.get('/quiz/editvquiz/{}'.format(vq.id)).data.decode()
    assert 'hide_answers' not in form and 'Release answers' not in teacher.get('/quiz/listvq').data.decode()
    assert teacher.post('/quiz/releasevq/{}'.format(vq.id)).status_code == 404
    assert teacher.post('/quiz/releasecq/{}'.format(cq.id)).status_code == 404


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
    # an average: no single attempt is marked as the one that counts
    assert 'Your score: 25%' in page and '★' not in page and 'Attempt 2' not in page
    # the teacher counts only sam's best attempt: that one is marked
    r = teacher.post('/quiz/retakerule/{}'.format(second.id), data={'rule': 'best'})
    assert r.status_code == 302
    page = sam.get('/mypage').data.decode()
    assert 'Your score: 50%' in page and '★ 50%' in page and '★ 0%' not in page
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
    assert 'data-attempts="{}"'.format(cq.id) in before and 'data-states="{}:new:"'.format(cq.id) in before
    assert 'class="badge badge-warn quiz-flag" hidden' in before
    with app.test_request_context():
        S.submit(cq, {1: '4'})
        new = S.retake(cq)
    after = sam.get('/mypage').data.decode()
    assert 'data-attempts="{},{}"'.format(cq.id, new.id) in after or 'data-attempts="{},{}"'.format(new.id, cq.id) in after
    assert 'data-states="{}:completed:100.0;{}:new:"'.format(cq.id, new.id) in after


def test_deleting_one_attempt_updates_the_students_quiz_box(app_db):
    # an attempt is one instance; the box on My quizzes holds all of a student's
    # attempts at one quiz and disappears with the last of them
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    from app.messages.models import Message
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Boxed', 'vplist': str(VProblem.query.one().id)})
    vq = VQuiz.query.one()
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam_id]})
    first = CQuiz.query.filter_by(assignee=sam_id).one()
    with app.test_request_context():
        S.submit(first, {1: '4'})
        second = S.retake(first)
    state = lambda: sam.get('/messages/poll?watch=mine').get_json()['watch']
    home = sam.get('/mypage').data.decode()
    assert home.count('class="box card quiz-card"') == 1 and 'data-attempts="{},{}"'.format(first.id, second.id) in home
    s0 = state()

    # the teacher deletes one attempt: the box stays with the other, and the page is told
    assert teacher.post('/quiz/delcq/{}'.format(second.id)).status_code == 302
    s1 = state()
    assert s1 != s0
    home = sam.get('/mypage').data.decode()
    assert 'data-attempts="{}"'.format(first.id) in home
    assert not Message.query.filter(Message.link == '/quiz/take/{}'.format(second.id)).count()  # its notices go too

    # the last attempt: the whole box goes
    teacher.post('/quiz/delcq/{}'.format(first.id))
    assert state() != s1
    home = sam.get('/mypage').data.decode()
    assert 'class="box card quiz-card"' not in home and 'Boxed' not in home
    assert not Message.query.filter(Message.link == '/quiz/take/{}'.format(first.id)).count()
    # the quiz itself still exists for the teacher, and deleting an assigned quiz is still refused
    assert VQuiz.query.get(vq.id) is not None
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam_id]})
    teacher.post('/quiz/delvq/{}'.format(vq.id))
    db.session.expire_all()
    assert VQuiz.query.get(vq.id) is not None
    # a teacher's My quizzes follows only their own attempts: sam's new one doesn't change it
    mine = teacher.get('/messages/poll?watch=mine').get_json()['watch']
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam_id]})
    assert mine is not None and teacher.get('/messages/poll?watch=mine').get_json()['watch'] == mine


def test_a_newly_assigned_quiz_says_new(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Fresh', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    home = sam.get('/mypage').data.decode()
    assert '<span class="badge badge-warn">New</span>' in home and 'Not started' not in home
    # opened: no longer new
    take_page(sam, CQuiz.query.one().id)
    home = sam.get('/mypage').data.decode()
    assert '<span class="badge badge-warn">New</span>' not in home and 'Started' in home


def test_view_problems_and_quizzes_without_editing(app_db):
    app, db = app_db
    from test_flow import AB
    from app.qgen.models import VProblem, VQuiz, CQuiz, CProblem
    teacher = login(app, 'teach')
    forms = [
        problem_form('numeric', 'Add', '[a] + [b] = ?', 'a + b', AB),
        problem_form('choice_one', 'Times', '[a] × [b] = ?', '', AB, choices='*[a*b]\n[a*b+1]\n[a+b]'),
        problem_form('choice_many', 'Evens', 'Which are even?', '', [], choices='*2\n*4\n3\n5'),
        problem_form('truefalse', 'Bigger', 'True or false: [a] > [b]', 'a > b', AB),
        problem_form('text', 'Capital', 'Capital of France?', 'Paris'),
        problem_form('essay', 'Why', 'Explain why.', 'Because.', [], grading_notes='x'),
    ]
    for f in forms:
        assert teacher.post('/quiz/makevprob', data=f).status_code == 302
    probs = VProblem.query.order_by(VProblem.id).all()
    # every problem: View on the list, three versions on its page
    plist = teacher.get('/quiz/listvp').data.decode()
    assert all('/quiz/viewvprob/{}'.format(p.id) in plist for p in probs)
    for p in probs:
        page = teacher.get('/quiz/viewvprob/{}'.format(p.id)).data.decode()
        assert page.count('class="card sample-item"') == 3, p.qtype
    assert 'Model answer (only you see it)' in teacher.get('/quiz/viewvprob/{}'.format(probs[-1].id)).data.decode()
    # a quiz with a group ("1 of these 2"): one student's version, numbered, answers hideable
    layout = json.dumps([probs[0].id, probs[1].id, {'pick': 1, 'from': [probs[2].id, probs[3].id]}])
    teacher.post('/quiz/makevquiz', data={'title': 'Viewable', 'vplist': layout})
    vq = VQuiz.query.one()
    assert '/quiz/viewvquiz/{}'.format(vq.id) in teacher.get('/quiz/listvq').data.decode()
    page = teacher.get('/quiz/viewvquiz/{}'.format(vq.id)).data.decode()
    assert page.count('class="card sample-item"') == 3  # 2 + 1 drawn from the group
    assert 'answers-off' in page and 'id="show-answers"' in page and '3 questions' in page
    # nothing was saved or sent, and students can't see these pages
    assert CQuiz.query.count() == 0 and CProblem.query.count() == 0
    sam = login(app, 'sam')
    assert sam.get('/quiz/viewvquiz/{}'.format(vq.id)).status_code == 302
    assert sam.get('/quiz/viewvprob/{}'.format(probs[0].id)).status_code == 302
    assert teacher.get('/quiz/viewvquiz/999999').status_code == 404


def test_attempt_rows_use_the_small_results_button(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Twice', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    with app.test_request_context():
        S.submit(cq, {1: '4'})
    # one attempt: the same one-line row, with the same small button
    assert 'btn btn-secondary btn-xs" href="/quiz/take/{}">Results</a>'.format(cq.id) in sam.get('/mypage').data.decode()
    with app.test_request_context():
        again = S.retake(cq)
        S.submit(again, {1: '4'})
    home = sam.get('/mypage').data.decode()
    # several attempts: one line each, ending in a small "Results" button
    assert home.count('class="attempt-row"') == 2 and home.count('btn-xs" href="/quiz/take/') == 2
    assert '>Results</a>' in home and '>View results</a>' not in home


def test_new_badge_stays_on_the_box_until_the_quiz_is_started(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Badge', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    new_badge = 'class="badge badge-warn quiz-new">New</span>'
    # on the box's title row, however often the page is opened, and shown once
    for _ in range(2):
        home = sam.get('/mypage').data.decode()
        assert home.count(new_badge) == 1 and home.count('>New</span>') == 2  # the box's, and the attempt's status
    take_page(sam, cq.id)  # started
    assert new_badge not in sam.get('/mypage').data.decode()
    with app.test_request_context():
        S.submit(cq, {1: '4'})
        S.retake(cq)  # a new attempt in the same box
    assert sam.get('/mypage').data.decode().count(new_badge) == 1


def test_quiz_box_says_how_many_attempts_it_holds(app_db):
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Count', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    assert '<span class="badge box-count">1 try</span>' in sam.get('/mypage').data.decode()
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    with app.test_request_context():
        S.submit(cq, {1: '4'})
        S.retake(cq)
    assert '<span class="badge box-count">2 tries</span>' in sam.get('/mypage').data.decode()


def test_every_attempt_on_my_quizzes_shows_its_date(app_db):
    app, db = app_db
    import re
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Dated', 'vplist': str(VProblem.query.one().id)})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    cq = CQuiz.query.filter_by(assignee=sam_id).one()
    rows = lambda: re.findall(r'<(?:div|li) class="attempt-row"><span class="nowrap">([^<]+)</span>', sam.get('/mypage').data.decode())
    assert rows() == [cq.when_label] and rows()[0].startswith('assigned ')  # a box with one attempt
    with app.test_request_context():
        S.submit(cq, {1: '4'})
    assert rows() == [CQuiz.query.get(cq.id).when_label]  # now the hand-in date and time
    with app.test_request_context():
        S.retake(cq)
    assert len(rows()) == 2  # several: each dated


def test_a_students_own_retake_rule_is_shown_where_the_quiz_is(app_db):
    # the quiz's rule applies to everyone except students given their own rule on
    # "Results by student": the quiz list, the quiz page and that page all say so
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Rules', 'vplist': str(VProblem.query.one().id), 'retake_rule': 'best'})
    vq = VQuiz.query.one()
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam_id]})
    cq = CQuiz.query.one()
    listing = teacher.get('/quiz/listvq').data.decode()
    assert 'retakes score best attempt' in listing and 'differs' not in listing
    assert 'have a different rule' not in teacher.get('/quiz/editvquiz/{}'.format(vq.id)).data.decode()
    S.set_retake_rule(cq, 'average')
    listing = teacher.get('/quiz/listvq').data.decode()
    assert '1 student differs' in listing
    page = teacher.get('/quiz/editvquiz/{}'.format(vq.id)).data.decode()
    assert '1 student has a different rule' in page and 'sam</a>: the average of all attempts' in page
    with app.test_request_context():
        S.submit(cq, {1: '4'})
        S.retake(cq)
    results = teacher.get('/quiz/listuser/{}'.format(sam_id)).data.decode()
    assert 'Just for sam' in results and "The quiz's own rule is the best attempt." in results

    # set back to the same rule as the quiz's: no longer a difference anywhere
    S.set_retake_rule(cq, 'best')
    assert all(c.retake_rule is None for c in CQuiz.query.all())  # follows the quiz again
    # (an old one saved the same as the quiz's, from before this, doesn't count either)
    for c in CQuiz.query.all():
        c.retake_rule = 'best'
    db.session.commit()
    listing = teacher.get('/quiz/listvq').data.decode()
    assert 'differs' not in listing
    assert 'have a different rule' not in teacher.get('/quiz/editvquiz/{}'.format(vq.id)).data.decode()
    assert 'Just for sam' not in teacher.get('/quiz/listuser/{}'.format(sam_id)).data.decode()
    assert S.retake_overrides(vq) == []
    from app import live
    with app.test_request_context():
        from flask_login import login_user
        login_user(User.query.filter_by(username='teach').one())
        assert live._quizzes(vq.id, None)[0][0][-1] == 0  # the quiz list's own count


def test_changing_the_quizs_retake_rule_applies_to_every_student(app_db):
    # students given their own rule go back to the quiz's when the quiz's rule changes;
    # saving the quiz without changing it leaves them alone
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    pid = str(VProblem.query.one().id)
    teacher.post('/quiz/makevquiz', data={'title': 'Rules', 'vplist': pid, 'retake_rule': 'best'})
    vq = VQuiz.query.one()
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [sam_id]})
    cq = CQuiz.query.one()
    with app.test_request_context():
        S.submit(cq, {1: '4'})
        S.retake(cq)
    S.set_retake_rule(cq, 'average')
    assert [c.retake_rule for c in CQuiz.query.all()] == ['average', 'average']
    page = teacher.get('/quiz/editvquiz/{}'.format(vq.id)).data.decode()
    assert 'Changing the setting above puts everyone on the new rule, this student too' in page

    # same rule: kept
    r = teacher.post('/quiz/editvquiz/{}'.format(vq.id), data={'title': 'Rules', 'vplist': pid, 'retake_rule': 'best'},
                     follow_redirects=True)
    assert 'applies to every student' not in r.data.decode()
    assert [c.retake_rule for c in CQuiz.query.all()] == ['average', 'average']

    # a new rule: everyone, sam included
    r = teacher.post('/quiz/editvquiz/{}'.format(vq.id), data={'title': 'Rules', 'vplist': pid, 'retake_rule': 'latest'},
                     follow_redirects=True)
    assert 'The new retake scoring now applies to every student, including the one who had their own.' in r.data.decode()
    db.session.expire_all()
    assert db.session.get(VQuiz, vq.id).retake_rule == 'latest'
    assert [c.retake_rule for c in CQuiz.query.all()] == [None, None]
    assert 'differs' not in teacher.get('/quiz/listvq').data.decode()
    # sam's own My quizzes and the teacher's Results by student count it the new way
    sam = login(app, 'sam')
    assert '(your latest try counts)' in sam.get('/mypage').data.decode()
    results = teacher.get('/quiz/listuser/{}'.format(sam_id)).data.decode()
    assert 'Just for sam' not in results and "The quiz's own rule" not in results

    # the same through the API
    from app.api.models import ApiToken
    S.set_retake_rule(CQuiz.query.first(), 'first')
    token = ApiToken.issue(db.session.get(User, User.query.filter_by(username='teach').one().id), 'test')[1]
    r = app.test_client().put('/api/v2/quizzes/{}'.format(vq.id), headers={'Authorization': 'Bearer ' + token},
                              json={'title': 'Rules', 'problems': [int(pid)], 'retake_rule': 'average'})
    assert r.status_code == 200
    db.session.expire_all()
    assert [c.retake_rule for c in CQuiz.query.all()] == [None, None]


def test_the_attempts_that_count_are_the_ones_marked(app_db):
    # the green ★ follows the retake rule, not just the highest score
    import re
    from types import SimpleNamespace as NS
    from app.qgen.models import counted_attempts, combined_score
    a, b, c = NS(id=1, score=100.0), NS(id=2, score=40.0), NS(id=3, score=70.0)
    done = [a, b, c]
    assert counted_attempts('best', done) == [a]
    assert counted_attempts('latest', done) == [c]
    assert counted_attempts('first', done) == [a]
    # an average of several scores: none of them is marked
    assert counted_attempts('average', done) == [] and counted_attempts('best2', done) == []
    assert counted_attempts('latest', []) == []
    # one finished attempt: its score is the score, whatever the rule
    for rule in ('best', 'latest', 'first', 'average', 'best2'):
        assert counted_attempts(rule, [b]) == [b]
    # the marked one's score is the score that counts
    for rule in ('best', 'latest', 'first'):
        assert counted_attempts(rule, done)[0].score == combined_score(rule, [x.score for x in done])

    # on the pages: 100% then 0%, scored by the latest attempt
    app, db = app_db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz
    from app.qgen import services as S
    sam_id = User.query.filter_by(username='sam').one().id
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'N', 'What is 2 + 2?', '4', []))
    teacher.post('/quiz/makevquiz', data={'title': 'Pick', 'vplist': str(VProblem.query.one().id), 'retake_rule': 'latest'})
    teacher.post('/quiz/assign', data={'vquiz': VQuiz.query.one().id, 'users': [sam_id]})
    first = CQuiz.query.one()
    with app.test_request_context():
        S.submit(first, {1: '4'})
        second = S.retake(first)
        S.submit(second, {1: '5'})
    stars = lambda html: re.findall(r'<span class="badge badge-ok"[^>]*>★ (\d+)%', html)
    sam = login(app, 'sam')
    assert stars(sam.get('/mypage').data.decode()) == ['0']
    assert stars(teacher.get('/quiz/listuser/{}'.format(sam_id)).data.decode()) == ['0']
    S.set_retake_rule(first, 'average')
    assert stars(sam.get('/mypage').data.decode()) == []
    assert '★' not in teacher.get('/quiz/listuser/{}'.format(sam_id)).data.decode()
    S.set_retake_rule(first, 'best')
    assert stars(teacher.get('/quiz/listuser/{}'.format(sam_id)).data.decode()) == ['100']


def test_the_browser_tab_icon(app_db):
    """The tab icon is the picture chosen in Settings, else the logo, made square; every
    page links to it, and its address changes when the picture does."""
    import io
    import os
    import re
    from PIL import Image
    app, db = app_db
    folder = app.config['STATIC_DIR']
    Image.new('RGB', (300, 60), (200, 30, 30)).save(os.path.join(folder, 'wide-logo.png'))
    Image.new('RGBA', (40, 40), (0, 90, 200, 255)).save(os.path.join(folder, 'tree.png'))
    anon = app.test_client()
    # nothing chosen and no logo: no icon (the browser shows its own)
    assert 'rel="icon"' not in anon.get('/login').data.decode()
    assert anon.get('/favicon.ico').status_code == 404
    teacher = login(app, 'teach')

    def icon_url(client, path='/login'):
        return re.search(r'rel="icon" type="image/png" sizes="32x32" href="([^"]+)"', client.get(path).data.decode()).group(1)

    def picture(r, size):
        assert r.status_code == 200 and r.mimetype == 'image/png'
        im = Image.open(io.BytesIO(r.data))
        assert im.size == (size, size)
        return im.convert('RGBA')

    # the logo, until a separate icon is chosen: a wide logo is centered, with clear space above and below
    teacher.post('/settings', data={'site_name': 'School', 'logo': 'wide-logo.png', 'code': ''})
    url = icon_url(anon)
    assert url.startswith('/site-icon/32.png?v=') and icon_url(teacher, '/dashboard') == url  # every page, signed in or not
    im = picture(anon.get(url), 32)
    assert im.getpixel((16, 16))[:3] == (200, 30, 30) and im.getpixel((16, 0))[3] == 0
    assert 'max-age=31536000' in anon.get(url).headers['Cache-Control']
    picture(anon.get('/favicon.ico'), 32)
    assert 'apple-touch-icon' in anon.get('/login').data.decode()
    picture(anon.get('/site-icon/180.png'), 180)
    assert anon.get('/site-icon/77.png').status_code == 404

    # a separate icon
    teacher.post('/settings', data={'site_name': 'School', 'logo': 'wide-logo.png', 'favicon': 'tree.png', 'code': ''})
    assert 'tree.png' in teacher.get('/settings').data.decode()
    new = icon_url(anon)
    assert new != url
    assert picture(anon.get(new), 32).getpixel((0, 0))[:3] == (0, 90, 200)
    # removing it brings back the logo
    teacher.post('/settings', data={'site_name': 'School', 'logo': 'wide-logo.png', 'favicon': '', 'code': ''})
    assert icon_url(anon) == url

    # a picture that isn't there, or outside the pictures folder: no icon, nothing breaks
    from app.qgen.models import Setting
    for bad in ('gone.png', '../config.py', '/etc/passwd'):
        Setting.put('favicon', bad)
        assert 'rel="icon"' not in anon.get('/login').data.decode()
        assert anon.get('/favicon.ico').status_code == 404


def test_the_calculator_comes_up_only_where_its_allowed(app_db):
    """A "Calculator allowed" quiz has the on-screen calculator, outside the quiz form so
    nothing typed in it is saved or handed in; a "No calculator" quiz has none."""
    app, db = app_db
    from app.qgen.models import CQuiz
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher, calculator_ok='y')
    sam_u = student(db, 'sam')
    assign(teacher, vq, [sam_u])
    cq = CQuiz.query.filter_by(assignee=sam_u.id).one()
    page = take_page(login(app, 'sam'), cq.id).data.decode()
    assert 'id="calc-open"' in page and 'id="calc"' in page and 'js/calculator.js' in page
    assert page.index('</form>') < page.index('id="calc"')  # not part of the answers
    vq.calculator_ok = False
    db.session.commit()
    page = login(app, 'sam').get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'No calculator' in page and 'calc-open' not in page and 'calculator.js' not in page

    # one problem that allows a calculator is enough, even with the quiz's own box unchecked
    add = next(p for p in vq.vproblems if p.title == 'Add')
    add.calculator_ok = True
    db.session.commit()
    page = login(app, 'sam').get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'Calculator allowed' in page and 'id="calc-open"' in page
    view = teacher.get('/quiz/viewvquiz/{}'.format(vq.id)).data.decode()
    assert 'Calculator allowed' in view and 'Because of: Add' in view
    from app.qgen.coach import quiz_hints
    hints = [h['text'] for h in quiz_hints('Q', [add.id], False, set(), {add.id: add})]
    assert 'Students will have a calculator: "Add" allows one.' in hints


def test_the_calculators_math():
    """static/js/calculator.js works things out itself (no eval); checked with node when it's installed."""
    import os
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    js = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'js', 'calculator.js')
    script = """
global.window = {}; require(%s); const c = window.qgenCalc;
const out = {};
for (const e of %s) { try { out[e] = c.format(c.evaluate(e, 42)); } catch (x) { out[e] = 'error: ' + x.msg; } }
console.log(JSON.stringify(out));
""" % (json.dumps(js), json.dumps(['2+3*4', '-2^2', '2^-1', '√9+1', '2π', '3(4+1)', 'sin 30', 'cos(90)', 'tan(45)',
                                    '0.1+0.2', '200*10%', '5²', '10÷4', '7−10', 'Ans/2', '1/3', '(3+4',
                                    '1/0', '√-4', 'tan(90)', '2 3', '3+', 'alert(1)']))
    got = json.loads(subprocess.run([node, '-e', script], capture_output=True, text=True, check=True).stdout)
    assert got == {'2+3*4': '14', '-2^2': '-4', '2^-1': '0.5', '√9+1': '4', '2π': '6.283185307', '3(4+1)': '15',
                   'sin 30': '0.5', 'cos(90)': '0', 'tan(45)': '1', '0.1+0.2': '0.3', '200*10%': '20', '5²': '25',
                   '10÷4': '2.5', '7−10': '-3', 'Ans/2': '21', '1/3': '0.3333333333', '(3+4': '7',
                   '1/0': "error: Can't divide by zero", '√-4': "error: Can't take the square root of a negative number",
                   'tan(90)': 'error: tan of 90° has no value', '2 3': "error: Something doesn't fit near the end",
                   '3+': 'error: Something is missing at the end',
                   'alert(1)': "error: “alert” isn't something the calculator knows"}


def test_results_by_quiz(app_db):
    """Each quiz with its students' attempts: the same rows as Results by student, the
    other way round; linked from the menu, the quiz list and Results by student."""
    app, db = app_db
    from app.qgen.models import CQuiz
    from app.qgen import services as S
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    assign(teacher, vq, [student(db, 'sam'), student(db, 'kim')])
    sam_q = CQuiz.query.filter_by(assignee=student(db, 'sam').id).one()
    with app.test_request_context():
        S.submit(sam_q, {1: '0', 2: []})
    page = teacher.get('/quiz/results').data.decode()
    assert 'Results by quiz' in page and 'Settings quiz' in page and '2 students' in page
    box = page.split('id="quiz-{}"'.format(vq.id))[1]
    assert box.index('kim</a>') < box.index('sam</a>')  # students by name
    assert 'not started' in box and '%</span>' in box and 'Details' in box and 'Archive' in box
    assert 'average 0%' in box  # sam's score counts; kim has none yet
    one = teacher.get('/quiz/results/{}'.format(vq.id)).data.decode()
    assert 'Results: Settings quiz' in one and 'id="quiz-{}"'.format(vq.id) in one and 'data-watch="quizresults:{}"'.format(vq.id) in one
    assert teacher.get('/quiz/results/99999').status_code == 302  # gone: back to Results by quiz
    # where it's linked from
    assert '/quiz/results' in teacher.get('/dashboard').data.decode()
    assert '/quiz/results/{}'.format(vq.id) in teacher.get('/quiz/listvq').data.decode()
    assert '/quiz/results"' in teacher.get('/quiz/listuser').data.decode()
    # teachers only
    assert login(app, 'sam').get('/quiz/results').status_code == 302
    # Results by student still draws the same rows
    by_student = teacher.get('/quiz/listuser/{}'.format(student(db, 'sam').id)).data.decode()
    assert 'Settings quiz' in by_student and 'Details' in by_student and 'Retake' in by_student


def test_unshuffled_order_warns_only_when_a_problem_is_the_same_for_everyone(app_db):
    """In a fixed order, "number 3 is B" only helps the student next door on a problem
    with no random values; when every problem's values are drawn per student, no warning."""
    app, db = app_db
    from app.qgen.coach import quiz_hints
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    probs = {p.title: p for p in vq.vproblems}
    add, evens = probs['Add'], probs['Evens']  # Add has a random value, Evens none

    def warned(chosen, shuffle):
        got = quiz_hints('Q', [p.id for p in chosen], False, set(), {p.id: p for p in chosen}, shuffle_order=shuffle)
        return [h['text'] for h in got if 'isn\'t shuffled' in h['text']]
    assert warned([add, evens], False) == ['Question order isn\'t shuffled, and "Evens" has no random values, so every '
                                           'student has the same answer there and "number 3 is B" is easier to pass along.']
    assert warned([add, evens], True) == []
    assert warned([add], False) == []  # every value is drawn for each student


def test_a_quiz_starts_only_from_its_start_card(app_db):
    """Opening a quiz shows what's ahead; nothing starts (nor its time limit) until "Start the quiz"."""
    app, db = app_db
    from app.qgen.models import CQuiz
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher, calculator_ok='y')
    sam_u = student(db, 'sam')
    assign(teacher, vq, [sam_u], time_limit='20')
    cq = CQuiz.query.filter_by(assignee=sam_u.id).one()
    sam = login(app, 'sam')
    card = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'Start the quiz' in card and '2 questions' in card and '20 minutes</strong> once you start' in card
    assert 'Calculator allowed' in card and 'saved as you go' in card and 'Hand it in' not in card
    db.session.expire_all()
    assert cq.startdate is None  # a look starts nothing

    # a teacher can't start it for them, and their view is the questions as before
    teacher.post('/quiz/take/{}/start'.format(cq.id))
    db.session.expire_all()
    assert cq.startdate is None
    assert 'Start the quiz' not in teacher.get('/quiz/take/{}'.format(cq.id)).data.decode()

    r = sam.post('/quiz/take/{}/start'.format(cq.id))
    assert r.status_code == 302 and r.headers['Location'].endswith('/quiz/take/{}'.format(cq.id))
    db.session.expire_all()
    started = cq.startdate
    assert started is not None
    page = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'value="Hand it in"' in page and 'id="timer"' in page
    sam.post('/quiz/take/{}/start'.format(cq.id))  # again: the time it started stays
    db.session.expire_all()
    assert cq.startdate == started


def test_the_start_card_says_when_it_closes(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    sam_u = student(db, 'sam')
    assign(teacher, vq, [sam_u])
    cq = CQuiz.query.filter_by(assignee=sam_u.id).one()
    sam = login(app, 'sam')
    assert 'No time limit.' in sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    # closing sooner than the time limit: that's how long they have
    cq.time_limit, cq.closes_at = 60, datetime.now() + timedelta(minutes=10)
    db.session.commit()
    card = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert 'so you\'ll have until then once you start' in card and '60 minutes' not in card
    cq.closes_at = datetime.now() + timedelta(days=2)
    db.session.commit()
    card = sam.get('/quiz/take/{}'.format(cq.id)).data.decode()
    assert '60 minutes</strong> once you start' in card and 'Hand it in by' in card
    # not open yet: no starting it early
    cq.opens_at = datetime.now() + timedelta(hours=1)
    db.session.commit()
    sam.post('/quiz/take/{}/start'.format(cq.id))
    db.session.expire_all()
    assert cq.startdate is None


def test_my_quizzes_has_an_in_progress_folder(app_db):
    """An automatic "In progress" entry after New: every quiz started and not handed in
    (each also stays in its own folder), with how many beside it."""
    app, db = app_db
    from app.qgen.models import CQuiz
    from app.qgen import services as S
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    sam_u = student(db, 'sam')
    assign(teacher, vq, [sam_u])
    sam = login(app, 'sam')
    cq = CQuiz.query.filter_by(assignee=sam_u.id).one()
    page = sam.get('/mypage?folder=started').data.decode()
    assert '✏️</span> In progress</a>' in page and 'Nothing in progress right now.' in page
    assert page.index('🆕</span> New</a>') < page.index('✏️</span> In progress</a>')
    take_page(sam, cq.id)
    page = sam.get('/mypage?folder=started').data.decode()
    assert 'In progress: quizzes you’ve started and not handed in' in page and 'Settings quiz' in page
    assert 'Nothing in progress' not in page
    row = page[page.index('✏️</span> In progress</a>'):]
    assert row[:row.index('</li>')].count('>1</span>') == 1  # its count
    # remembered like any folder: back to My quizzes shows it again
    assert 'In progress: quizzes' in sam.get('/mypage').data.decode()
    S.submit(cq, {1: '4'})
    assert 'Nothing in progress right now.' in sam.get('/mypage?folder=started').data.decode()


def test_a_quiz_with_a_try_still_to_do_is_to_do_even_if_a_later_one_is_done(app_db):
    """Given twice and the newer copy handed in first: the older one still waits, so the quiz
    is first on My quizzes with Start in its heading, "not handed in" for teachers, and no other retake is offered."""
    app, db = app_db
    from app.qgen.models import CQuiz
    from app.qgen import services as S
    teacher = login(app, 'teach')
    vq = make_quiz(app, db, teacher)
    sam_u = student(db, 'sam')
    assign(teacher, vq, [sam_u])
    assign(teacher, vq, [sam_u])
    older, newer = CQuiz.query.filter_by(assignee=sam_u.id).order_by(CQuiz.id).all()
    S.submit(newer, {1: '4'})
    page = login(app, 'sam').get('/mypage?folder=all').data.decode()
    card = page[page.index('data-quiz="{}"'.format(vq.id)):]
    card = card[:card.index('</summary>')]
    assert '>Start</a>' in card  # its heading offers the try still waiting
    results = teacher.get('/quiz/results/{}'.format(vq.id)).data.decode()
    assert 'data-state="out"' in results
    student_page = teacher.get('/quiz/listuser/{}'.format(sam_u.id)).data.decode()
    assert 'Give sam another attempt' not in student_page
    S.submit(older, {1: '4'})  # all handed in: nothing to start, and a retake can be given again
    page = login(app, 'sam').get('/mypage?folder=all').data.decode()
    card = page[page.index('data-quiz="{}"'.format(vq.id)):]
    assert '>Start</a>' not in card[:card.index('</summary>')]
    assert 'Give sam another attempt' in teacher.get('/quiz/listuser/{}'.format(sam_u.id)).data.decode()
