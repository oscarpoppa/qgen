"""Short text answers checked at hand-in (any-order lists, then one small AI call) and a teacher changing the
grades of a finished attempt (the owner, 2026-10-25, CP3/CP4/CP9; fixes from the code critic the same day)."""
import json

from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)


def ids(name):
    from app.user.models import User
    return User.query.filter_by(username=name).one().id


def text_quiz(teacher, accepted):
    """A quiz of one Short text problem with these accepted answers; returns it."""
    from app.qgen.models import VProblem, VQuiz
    teacher.post('/quiz/makevprob', data=problem_form('text', 'Names', 'Who?', accepted, [], same_ok='1'))
    vp = VProblem.query.order_by(VProblem.id.desc()).first()
    teacher.post('/quiz/makevquiz', data={'title': 'Names quiz', 'vplist': str(vp.id), 'keep_order': 'y'})
    return VQuiz.query.filter_by(title='Names quiz').one()


def give(teacher, vq, who='sam'):
    from app.qgen.models import CQuiz
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids(who)]})
    return CQuiz.query.filter_by(vquiz_id=vq.id).order_by(CQuiz.id.desc()).first()


def test_a_list_in_any_order_but_not_a_name_with_and():
    from app.qgen.qtypes import list_match
    assert list_match('mark john luke matthew', 'matthew, mark, luke, and john')
    assert list_match('john and mark', 'mark, john')
    assert not list_match('mark mark john', 'matthew, mark, luke, and john')
    # one answer with "and" in it is not a list (the code critic, 2026-10-25)
    assert not list_match('clark lewis', 'lewis and clark')
    assert not list_match('roll and rock', 'rock and roll')


def test_the_ai_looks_at_hand_in_and_only_a_right_counts(app_db, monkeypatch):
    app, db = app_db
    from app import tuning
    from app.qgen import ai_helper, services as S
    from app.qgen.models import AICall
    teacher = login(app, 'teach')
    vq = text_quiz(teacher, 'photosynthesis')
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    asked = []

    def fake(key, items, client=None):
        asked.append(items)
        return {items[0]['n']: True}, {'input_tokens': 10, 'output_tokens': 5}
    monkeypatch.setattr(ai_helper, 'check_short_answers', fake)
    try:
        cq = give(teacher, vq)
        with app.test_request_context():
            assert S.submit(cq, {1: 'photo synthesis'}) != 'review'
        cp = cq.cproblems[0]
        assert cp.credit == 1.0 and cp.conc_opts.get('ai_right') and not cq.needs_review and cq.score == 100
        assert len(asked) == 1 and asked[0][0]['answer'] == 'photo synthesis'
        assert AICall.query.filter_by(kind='grade', ok=True).count() == 1
        # turned off in Settings: nothing asked, the teacher grades it
        from app.qgen.models import Setting
        Setting.put('tune.ai_short_answers', 'off')
        cq = give(teacher, vq)
        with app.test_request_context():
            assert S.submit(cq, {1: 'photo synthesis'}) == 'review'
        assert len(asked) == 1 and cq.cproblems[0].credit is None
    finally:
        app.config['ANTHROPIC_API_KEY'] = None


def test_the_deadline_sweep_never_waits_for_the_ai(app_db, monkeypatch):
    """Attempts handed in by the once-a-minute sweep (inside someone's page request) go to the teacher
    without an AI call (the code critic, 2026-10-25)."""
    app, db = app_db
    from datetime import datetime, timedelta
    from app.qgen import ai_helper, services as S
    teacher = login(app, 'teach')
    vq = text_quiz(teacher, 'photosynthesis')
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    asked = []
    monkeypatch.setattr(ai_helper, 'check_short_answers', lambda key, items, client=None: asked.append(items) or ({1: True}, {}))
    try:
        cq = give(teacher, vq)
        #(started, with an answer autosaved, then the quiz closed)
        cq.startdate = datetime.now() - timedelta(minutes=20)
        cq.cproblems[0].submitted = 'photo synthesis'
        cq.closes_at = datetime.now() - timedelta(minutes=5)
        db.session.commit()
        with app.test_request_context():
            assert S.close_expired() == 1
        assert cq.needs_review and cq.cproblems[0].credit is None and not asked
    finally:
        app.config['ANTHROPIC_API_KEY'] = None


def test_a_teacher_changes_the_grades_of_a_finished_attempt(app_db):
    app, db = app_db
    from app.qgen import services as S
    from app.messages.models import Message
    teacher = login(app, 'teach')
    vq = text_quiz(teacher, 'photosynthesis')
    cq = give(teacher, vq)
    with app.test_request_context():
        S.submit(cq, {1: 'photosynthesis'})
    assert cq.completed and cq.score == 100
    cp = cq.cproblems[0]
    with app.test_request_context():
        assert S.change_grades(cq, {cp.id: {'credit': 50, 'feedback': 'Half: spelled out?'}}, ids('teach')) == []
    db.session.expire_all()
    assert cq.score == 50 and cp.credit == 0.5 and cp.feedback == 'Half: spelled out?'
    assert cq.changed_by == ids('teach') and cq.changed_date is not None
    assert Message.query.filter(Message.student_id == ids('sam'), Message.body.like('Your teacher changed the grades on “Names quiz”: now 50%.')).count() == 1
    # the student's answer stays as it was; a credit out of range is refused
    assert cp.submitted == 'photosynthesis'
    import pytest
    with app.test_request_context(), pytest.raises(S.ServiceError):
        S.change_grades(cq, {cp.id: {'credit': 150}}, ids('teach'))
    # the page: teachers only
    assert login(app, 'sam').get('/quiz/review/{}/change'.format(cq.id)).status_code in (302, 403)
    assert teacher.get('/quiz/review/{}/change'.format(cq.id)).status_code == 200
