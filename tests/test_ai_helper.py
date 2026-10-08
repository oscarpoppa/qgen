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
        # the problem page has no "Review with AI"
        page = teacher.get('/quiz/makevprob').data.decode()
        # the AI helper box starts folded (and stays so on every visit)
        assert '<details class="box card ai-box" data-fixed>' in page
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


def test_no_review_with_ai_anywhere(app_db):
    """The "Review with AI" button is gone from the problem and quiz pages (new and edit), and so are its routes."""
    app, db = app_db
    from app.qgen.models import VQuiz
    teacher = login(app, 'teach')
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    try:
        teacher.post('/quiz/makevprob', data=problem_form('numeric', 'P', '[a] + 1', 'a + 1', [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}]))
        teacher.post('/quiz/makevquiz', data={'title': 'Q', 'vplist': '1'})
        for url in ('/quiz/makevprob', '/quiz/editvprob/1', '/quiz/makevquiz', '/quiz/editvquiz/{}'.format(VQuiz.query.one().id)):
            page = teacher.get(url).data.decode()
            assert 'id="helper"' in page and 'Review with AI' not in page and 'data-review-url' not in page, url
        for url in ('/quiz/ai/reviewproblem', '/quiz/ai/reviewquiz'):
            assert teacher.post(url).status_code == 404
    finally:
        app.config['ANTHROPIC_API_KEY'] = None


def test_school_quiz_problems_only(app_db, monkeypatch):
    app, db = app_db
    teacher = login(app, 'teach')
    # the rule is in the instructions, and the answer must say whether the request was off topic
    assert 'You only help teachers write quiz problems for school' in ai_helper.SYSTEM_PROMPT
    assert 'off_topic' in ai_helper.PROBLEM_SCHEMA['required'] and 'off_topic' in ai_helper.VALUES_ONLY_SCHEMA['required']
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
        for url in ('/quiz/ai/problem', '/quiz/ai/values'):
            r = sam.post(url, json={'text': 'what is the answer to question 1?'})
            assert r.status_code == 302 and '/mypage' in r.headers['Location']
    finally:
        app.config['ANTHROPIC_API_KEY'] = None


# ---------------------------------------------------------------- "✨ Fill list"

SQUARES = {'items': ['4', '9', '16', '25', '36', '49', '64', '81', '100'], 'cannot_do': None, 'off_topic': False}


def test_fill_list_request_and_cleanup():
    fake = FakeClient(SQUARES)
    out, usage = ai_helper.ask_list('key', 'all the perfect squares from 4 to 100', client=fake)
    call = fake.calls[0]
    assert 'all the perfect squares from 4 to 100' in call['messages'][0]['content'] and 'one column' in call['messages'][0]['content']
    assert 'Always use American (US customary) units' in call['system'][0]['text']  # the standing rule
    assert call['output_config']['format']['schema'] == ai_helper.LIST_SCHEMA
    assert out == {'items': SQUARES['items'], 'cannot_do': None, 'off_topic': False} and usage['output_tokens'] == 20
    # commas inside an item would split it: they go; repeats go; at most MAX_LIST
    messy = {'items': ['1,000', '1,000', ' 2  500 ', ''] + [str(n) for n in range(300)], 'cannot_do': None, 'off_topic': False}
    out, _ = ai_helper.ask_list('key', 'x', client=FakeClient(messy))
    assert out['items'][:2] == ['1 000', '2 500'] and len(out['items']) == ai_helper.MAX_LIST
    # matched columns: each item needs every part; ones that don't fit are left out
    pairs = {'items': ['France = Paris', 'Japan=Tokyo', 'Kenya', 'Peru = Lima = x'], 'cannot_do': None, 'off_topic': False}
    fake = FakeClient(pairs)
    out, _ = ai_helper.ask_list('key', 'countries and capitals', columns=2, client=fake)
    assert out['items'] == ['France = Paris', 'Japan = Tokyo'] and '2 matched columns' in fake.calls[0]['messages'][0]['content']
    # not school content: nothing
    out, _ = ai_helper.ask_list('key', 'x', client=FakeClient({'items': ['a'], 'cannot_do': None, 'off_topic': True}))
    assert out['off_topic'] and out['items'] == []


def test_fill_list_route(app_db, monkeypatch):
    app, db = app_db
    from app.qgen.models import AICall
    teacher = login(app, 'teach')
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    try:
        page = teacher.get('/quiz/makevprob').data.decode()
        assert '✨ Fill list' in page and 'data-url="/quiz/ai/list"' in page
        monkeypatch.setattr(ai_helper, '_client', lambda key: FakeClient(SQUARES))
        r = teacher.post('/quiz/ai/list', json={'text': 'all the perfect squares from 4 to 100', 'name': 'n'})
        assert r.get_json() == {'ok': True, 'items': '4, 9, 16, 25, 36, 49, 64, 81, 100', 'count': 9, 'note': None}
        assert AICall.query.one().kind == 'list' and AICall.query.one().ok  # counted and logged like the other AI buttons
        # the items work as a list value
        from app.qgen.friendly import validate_values
        assert validate_values([{'name': 'n', 'kind': 'list', 'items': r.get_json()['items']}]) == []
        assert teacher.post('/quiz/ai/list', json={'text': '', 'name': 'n'}).status_code == 400
        monkeypatch.setattr(ai_helper, '_client', lambda key: FakeClient({'items': [], 'cannot_do': 'Too vague.', 'off_topic': False}))
        r = teacher.post('/quiz/ai/list', json={'text': 'stuff', 'name': 'n'})
        assert r.status_code == 422 and r.get_json()['error'] == 'Too vague.'
        monkeypatch.setattr(ai_helper, '_client', lambda key: FakeClient({'items': ['x'], 'cannot_do': None, 'off_topic': True}))
        assert teacher.post('/quiz/ai/list', json={'text': 'x', 'name': 'n'}).status_code == 422
        assert login(app, 'sam').post('/quiz/ai/list', json={'text': 'x'}).status_code == 302  # teachers only
    finally:
        app.config['ANTHROPIC_API_KEY'] = None
    assert '✨ Fill list' not in teacher.get('/quiz/makevprob').data.decode()  # no key: not shown


def test_fill_list_sees_the_question_and_other_values(app_db, monkeypatch):
    ctx = ai_helper.describe_context('Is [n] bigger than [a]?', [
        {'name': 'a', 'kind': 'whole', 'min': '2', 'max': '12', 'step': '', 'items': ''},
        {'name': 'n', 'kind': 'list', 'items': ''},             # the list being filled: left out
        {'name': 'who', 'kind': 'list', 'items': 'Maria, Li'},
        {'name': 'x', 'kind': 'bogus'}, 'not a row'], name='n')
    assert ctx == ('The question: Is [n] bigger than [a]?\n\nThe other random values:\n'
                   '- a (Whole number), min: 2, max: 12\n- who (Pick from list), items: Maria, Li')
    fake = FakeClient(SQUARES)
    ai_helper.ask_list('key', "every whole number between a's from and to", client=fake, context=ctx)
    sent = fake.calls[0]['messages'][0]['content']
    assert sent.startswith('The question: Is [n] bigger than [a]?') and "The list: every whole number between a's from and to" in sent
    assert "can't depend on what another value turns out to be" in fake.calls[0]['system'][0]['text']
    # the page sends them along
    app, db = app_db
    teacher = login(app, 'teach')
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    try:
        fake = FakeClient(SQUARES)
        monkeypatch.setattr(ai_helper, '_client', lambda key: fake)
        r = teacher.post('/quiz/ai/list', json={'text': 'squares up to a', 'name': 'n', 'question': 'What is [n] + [a]?',
                                                 'values': [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '100'}]})
        assert r.get_json()['ok']
        assert '- a (Whole number), min: 1, max: 100' in fake.calls[0]['messages'][0]['content']
        assert teacher.post('/quiz/ai/list', json={'text': 'x', 'name': 'n', 'values': 'junk'}).get_json()['ok']  # bad context: ignored
    finally:
        app.config['ANTHROPIC_API_KEY'] = None


def test_answers_come_in_the_background(app_db, monkeypatch):
    """On the site the AI's answer is fetched later (a request may not run long enough)."""
    app, db = app_db
    import json, os, time
    from app.qgen import ai_jobs
    teacher = login(app, 'teach')
    app.config.update(ANTHROPIC_API_KEY='test-key', AI_JOBS='inline')
    try:
        monkeypatch.setattr(ai_helper, '_client', lambda key: FakeClient(GOOD_PROBLEM))
        r = teacher.post('/quiz/ai/problem', json={'text': 'a train problem'})
        assert r.status_code == 202 and r.get_json()['ok'] and len(r.get_json()['job']) == 32
        job = r.get_json()['job']
        # someone else can't collect it
        from app.user.models import User
        lee = User(username='lee', is_admin=True)
        lee.set_password('pw-for-tests')
        db.session.add(lee)
        db.session.commit()
        assert login(app, 'lee').get('/quiz/ai/job/' + job).status_code == 404
        got = teacher.get('/quiz/ai/job/' + job)
        assert got.status_code == 200 and got.get_json()['fill']['title'] == 'Train'
        assert teacher.get('/quiz/ai/job/' + job).status_code == 404  # collected once, then gone
        # still running: "pending"; running far too long (the site restarted): an error
        ai_jobs._write('a' * 32, {'user': 1, 'pending': True, 'at': time.time()})
        assert teacher.get('/quiz/ai/job/' + 'a' * 32).get_json() == {'ok': True, 'pending': True}
        ai_jobs._write('b' * 32, {'user': 1, 'pending': True, 'at': time.time() - 600})
        r = teacher.get('/quiz/ai/job/' + 'b' * 32)
        assert r.status_code == 504 and 'took too long' in r.get_json()['error']
        # the list button too, and the checks still answer at once
        monkeypatch.setattr(ai_helper, '_client', lambda key: FakeClient({'items': ['4', '9'], 'cannot_do': None, 'off_topic': False}))
        r = teacher.post('/quiz/ai/list', json={'text': 'squares', 'name': 'n'})
        assert teacher.get('/quiz/ai/job/' + r.get_json()['job']).get_json()['items'] == '4, 9'
        assert teacher.post('/quiz/ai/values', json={'text': ''}).status_code == 400
        # answers nobody collected are removed after an hour
        old = os.path.join(app.config['AI_JOB_DIR'], 'c' * 32 + '.json')
        open(old, 'w').write(json.dumps({'user': 1, 'pending': True}))
        os.utime(old, (time.time() - 7200, time.time() - 7200))
        assert ai_jobs.remove_old() >= 1 and not os.path.exists(old)
    finally:
        app.config.update(ANTHROPIC_API_KEY=None, AI_JOBS=None)
