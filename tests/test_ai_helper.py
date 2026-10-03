"""The AI helper, with a stand-in for the Claude API (no key, no cost)."""
import json
from types import SimpleNamespace

import pytest

from app.qgen import ai_helper
from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)


class FakeClient:
    """Answers like the Claude API would, and remembers what it was asked."""
    def __init__(self, payload=None, stop_reason='end_turn', error=None):
        self.payload, self.stop_reason, self.error, self.calls = payload, stop_reason, error, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        text = json.dumps(self.payload) if not isinstance(self.payload, str) else self.payload
        return SimpleNamespace(stop_reason=self.stop_reason, usage=SimpleNamespace(input_tokens=10, output_tokens=20),
                               content=[SimpleNamespace(type='text', text=text)])


GOOD_PROBLEM = {'qtype': 'numeric', 'title': 'Train', 'question': 'A train goes [speed] mph for [hours] hours. How far?',
                'values': [{'name': 'speed', 'kind': 'whole', 'min': '40', 'max': '80', 'step': '5', 'places': None, 'nonzero': False,
                            'items': None, 'pick_n': None, 'formula': None, 'im_min': None, 'im_max': None, 'different_from': []},
                           {'name': 'hours', 'kind': 'whole', 'min': '2', 'max': '5', 'step': None, 'places': None, 'nonzero': False,
                            'items': None, 'pick_n': None, 'formula': None, 'im_min': None, 'im_max': None, 'different_from': []}],
                'answer': 'speed * hours', 'choices': None, 'combos': None, 'show_n': None, 'case_sensitive': False,
                'grading_notes': None, 'cannot_do': None}


def test_request_shape():
    fake = FakeClient(GOOD_PROBLEM)
    fill, usage = ai_helper.ask('key', 'problem', 'a train problem', client=fake)
    call = fake.calls[0]
    assert call['model'] == 'claude-opus-5' and call['fallbacks'] == 'default'
    assert call['output_config']['format']['type'] == 'json_schema'
    assert call['system'][0]['cache_control'] == {'type': 'ephemeral'}
    assert 'a train problem' in call['messages'][0]['content']
    assert 'Always use American (US customary) units' in call['system'][0]['text'] and 'miles per hour (mph)' in call['system'][0]['text']  # the teacher's standing rule
    assert fill['values'][0] == {'name': 'speed', 'kind': 'whole', 'min': '40', 'max': '80', 'step': '5'}
    assert usage == {'input_tokens': 10, 'output_tokens': 20}
    assert ai_helper.problems_with(fill, 'problem') == []


def test_bad_output_is_checked_like_typed_input():
    bad = dict(GOOD_PROBLEM, qtype='nonsense', answer='__import__("os")')
    fill, _ = ai_helper.ask('key', 'problem', 'x', client=FakeClient(bad))
    assert fill['qtype'] == 'numeric'  # unknown types fall back safely
    assert ai_helper.problems_with(fill, 'problem')  # the formula is refused by the normal checks


def test_cannot_do_is_passed_on():
    vals = {'values': [], 'cannot_do': 'I couldn\'t do "prime numbers only"; use a list instead.'}
    fill, _ = ai_helper.ask('key', 'values', 'primes', client=FakeClient(vals))
    assert 'prime' in fill['cannot_do']


@pytest.mark.parametrize('stop, message', [('refusal', 'declined'), ('max_tokens', 'too long')])
def test_refusal_and_truncation(stop, message):
    with pytest.raises(ai_helper.AIError, match=message):
        ai_helper.ask('key', 'problem', 'x', client=FakeClient(GOOD_PROBLEM, stop_reason=stop))


def test_unreadable_answer():
    with pytest.raises(ai_helper.AIError, match="couldn't read"):
        ai_helper.ask('key', 'problem', 'x', client=FakeClient('not json'))


def test_review():
    fake = FakeClient({'suggestions': [{'level': 'warn', 'text': 'Say whether to round.'}, {'level': 'odd', 'text': 'Nice.'}]})
    tips, _ = ai_helper.review('key', 'Question: ...', client=fake)
    assert 'a measurement not in American units' in fake.calls[0]['system'][0]['text']
    assert tips == [{'level': 'warn', 'text': 'Say whether to round.', 'action': None},
                    {'level': 'tip', 'text': 'Nice.', 'action': None}]


def test_routes_guard_key_limit_and_log(app_db, monkeypatch):
    app, db = app_db
    from app.qgen.models import AICall
    teacher = login(app, 'teach')
    body = {'text': 'a train problem'}
    app.config['ANTHROPIC_API_KEY'] = None
    r = teacher.post('/quiz/ai/problem', json=body)
    assert r.status_code == 400 and 'no API key' in r.get_json()['error']
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    try:
        monkeypatch.setattr(ai_helper, '_client', lambda key: FakeClient(GOOD_PROBLEM))
        r = teacher.post('/quiz/ai/problem', json=body)
        assert r.get_json()['ok'] and r.get_json()['fill']['title'] == 'Train'
        assert AICall.query.one().ok and AICall.query.one().output_tokens == 20
        assert teacher.post('/quiz/ai/values', json={'text': ''}).status_code == 400
        # the problem page has no "Review with AI" (the quiz builder still has its own)
        page = teacher.get('/quiz/makevprob').data.decode()
        assert 'Fill in for me' in page and 'Review with AI' not in page and 'data-review-url' not in page
        from app.qgen.models import VProblem
        teacher.post('/quiz/makevprob', data=problem_form('numeric', 'T', '[a] + 1', 'a + 1', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}]))
        edit = teacher.get('/quiz/editvprob/{}'.format(VProblem.query.first().id)).data.decode()
        assert 'id="helper"' in edit and 'Review with AI' not in edit and 'data-review-url' not in edit  # editing too
        assert teacher.post('/quiz/ai/reviewproblem').status_code == 404
        # hourly limit
        from app import tuning
        for _ in range(tuning.get('ai_hourly')):
            db.session.add(AICall(user_id=1, kind='values', request='x', ok=True))
        db.session.commit()
        r = teacher.post('/quiz/ai/problem', json=body)
        assert r.status_code == 429
        # students can't use it
        assert login(app, 'sam').post('/quiz/ai/problem', json=body).status_code == 302
    finally:
        app.config['ANTHROPIC_API_KEY'] = None


def test_ai_boxes_hidden_without_key(app_db):
    app, db = app_db
    app.config['ANTHROPIC_API_KEY'] = None
    page = login(app, 'teach').get('/quiz/makevprob').data.decode()
    assert 'Fill in for me' not in page and 'Review with AI' not in page and 'id="helper"' in page


def test_review_whole_quiz_describes_groups(app_db, monkeypatch):
    app, db = app_db
    from app.qgen.models import VProblem
    teacher = login(app, 'teach')
    for n in range(3):
        teacher.post('/quiz/makevprob', data=problem_form('numeric', 'P{}'.format(n), '[a] + {}'.format(n), 'a + {}'.format(n),
                                                          [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}]))
    ids = [p.id for p in VProblem.query.order_by(VProblem.id)]
    fake = FakeClient({'suggestions': [{'level': 'tip', 'text': 'Nice mix.'}]})
    monkeypatch.setattr(ai_helper, '_client', lambda key: fake)
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    try:
        r = teacher.post('/quiz/ai/reviewquiz', data={'title': 'Week 2', 'shuffle_order': 'y',
                                                      'vplist': json.dumps([ids[0], {'pick': 1, 'from': ids[1:]}])})
        assert r.get_json()['hints'][0]['text'] == 'Nice mix.'
        sent = fake.calls[0]['messages'][0]['content']
        assert 'Week 2' in sent and 'each student gets 1 of these 2' in sent and 'P2' in sent
    finally:
        app.config['ANTHROPIC_API_KEY'] = None


def test_school_quiz_problems_only(app_db, monkeypatch):
    app, db = app_db
    teacher = login(app, 'teach')
    # the rule is in the instructions, and the answer must say whether the request was off topic
    assert 'You only help teachers write quiz problems for school' in ai_helper.SYSTEM_PROMPT
    assert 'off_topic' in ai_helper.PROBLEM_SCHEMA['required'] and 'off_topic' in ai_helper.VALUES_ONLY_SCHEMA['required']
    assert 'Only review school quiz material' in ai_helper.REVIEW_PROMPT
    off = dict(GOOD_PROBLEM, off_topic=True, cannot_do='I only write school quiz problems.')
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    try:
        # an off-topic request fills in nothing, even if the answer carried content
        monkeypatch.setattr(ai_helper, '_client', lambda key: FakeClient(off))
        for kind in ('problem', 'values'):
            r = teacher.post('/quiz/ai/' + kind, json={'text': 'write a birthday email to my aunt'})
            assert r.status_code == 422 and r.get_json()['ok'] is False and 'fill' not in r.get_json()
            assert 'only writes school quiz problems' in r.get_json()['error']
        # a school problem still works
        monkeypatch.setattr(ai_helper, '_client', lambda key: FakeClient(dict(GOOD_PROBLEM, off_topic=False)))
        assert teacher.post('/quiz/ai/problem', json={'text': 'a train problem'}).get_json()['ok']
        # students can't reach any AI action (so they can't ask it for answers)
        sam = login(app, 'sam')
        for url in ('/quiz/ai/problem', '/quiz/ai/values', '/quiz/ai/reviewquiz'):
            r = sam.post(url, json={'text': 'what is the answer to question 1?'})
            assert r.status_code == 302 and '/mypage' in r.headers['Location']
    finally:
        app.config['ANTHROPIC_API_KEY'] = None
