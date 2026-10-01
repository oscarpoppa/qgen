"""The REST API (/api/v2), the locked /api/v1, and the automatic closing of overdue quizzes."""
import json
from datetime import datetime, timedelta

from test_flow import app_db  # noqa: F401  (fixture)


class Api:
    """A tiny API client for tests: remembers its token."""
    def __init__(self, app, username=None):
        self.c, self.token = app.test_client(), None
        if username:
            r = self.c.post('/api/v2/tokens', json={'username': username, 'password': 'pw-for-tests', 'name': 'test'})
            assert r.status_code == 201, r.get_json()
            self.token = r.get_json()['token']

    def call(self, method, path, **kw):
        headers = {'Authorization': 'Bearer ' + self.token} if self.token else {}
        return getattr(self.c, method)('/api/v2' + path, headers=headers, **kw)

    def get(self, path, **kw): return self.call('get', path, **kw)
    def post(self, path, **kw): return self.call('post', path, **kw)
    def put(self, path, **kw): return self.call('put', path, **kw)
    def delete(self, path, **kw): return self.call('delete', path, **kw)


A = {'name': 'a', 'kind': 'whole', 'min': 2, 'max': 40}
B = {'name': 'b', 'kind': 'whole', 'min': 2, 'max': 40, 'different_from': ['a']}


def make_quiz(t, hide_answers=False):
    ids = []
    for p in [
        {'type': 'numeric', 'title': 'Add', 'question': '[a] + [b] = ?', 'answer': 'a + b', 'options': {'values': [A, B]}},
        {'type': 'choice_one', 'title': 'Times', 'question': '[a] × [b] = ?', 'options': {'values': [A, B], 'choices': '*[a*b]\n[a*b+1]\n[a+b]'}},
        {'type': 'choice_many', 'title': 'Evens', 'question': 'Which are even?', 'options': {'choices': '*2\n*4\n3\n5'}},
        {'type': 'essay', 'title': 'Why', 'question': 'Explain why.', 'options': {'grading_notes': 'Mentions inertia'}},
    ]:
        r = t.post('/problems', json=p)
        assert r.status_code == 201, r.get_json()
        ids.append(r.get_json()['id'])
    r = t.post('/quizzes', json={'title': 'API quiz', 'problems': ids, 'hide_answers': hide_answers})
    assert r.status_code == 201, r.get_json()
    return r.get_json()['id'], ids


def student_ids(db):
    from app.user.models import User
    return {u.username: u.id for u in User.query.filter_by(is_admin=False)}


# ---------------------------------------------------------------- sign-in

def test_tokens_sign_in_list_revoke(app_db):
    app, db = app_db
    from app.api.models import ApiToken
    anon = Api(app)
    assert anon.get('/me').status_code == 401
    assert anon.get('/me').headers['WWW-Authenticate'] == 'Bearer'
    r = anon.post('/tokens', json={'username': 'sam', 'password': 'nope'})
    assert r.status_code == 401 and r.get_json()['error']['code'] == 'unauthorized'
    assert anon.post('/tokens', data='not json').status_code == 400
    sam = Api(app, 'sam')
    me = sam.get('/me').get_json()
    assert me['username'] == 'sam' and me['is_teacher'] is False
    # only a fingerprint is stored
    row = ApiToken.query.one()
    assert sam.token.startswith('qg_') and sam.token not in (row.token_hash, row.prefix) and len(row.token_hash) == 64
    listed = sam.get('/tokens').get_json()['tokens']
    assert listed[0]['current'] and 'token' not in listed[0]
    # a second device, then revoke it
    other = Api(app, 'sam')
    tid = [t['id'] for t in sam.get('/tokens').get_json()['tokens'] if not t['current']][0]
    assert sam.delete('/tokens/{}'.format(tid)).status_code == 204
    assert other.get('/me').status_code == 401
    # another user's token can't be revoked
    kim = Api(app, 'kim')
    assert kim.delete('/tokens/{}'.format(row.id)).status_code == 404
    # sign out
    assert sam.delete('/tokens/current').status_code == 204 and sam.get('/me').status_code == 401
    # expired
    k = ApiToken.query.filter_by(user_id=kim.get('/me').get_json()['id']).one()
    k.expires_at = datetime.now() - timedelta(seconds=1)
    db.session.commit()
    assert kim.get('/me').status_code == 401


def test_password_guessing_is_throttled(app_db):
    app, db = app_db
    anon = Api(app)
    for _ in range(10):
        assert anon.post('/tokens', json={'username': 'sam', 'password': 'wrong'}).status_code == 401
    r = anon.post('/tokens', json={'username': 'sam', 'password': 'pw-for-tests'})
    assert r.status_code == 429 and r.get_json()['error']['code'] == 'too_many_attempts'
    # other accounts aren't affected
    assert anon.post('/tokens', json={'username': 'kim', 'password': 'pw-for-tests'}).status_code == 201


def test_reset_password_blocks_api(app_db):
    app, db = app_db
    from app.user.models import User
    sam = Api(app, 'sam')
    u = User.query.filter_by(username='sam').one()
    u.pw_man_reset = True
    db.session.commit()
    assert sam.get('/me').get_json()['error']['code'] == 'password_change_required'
    assert Api(app).post('/tokens', json={'username': 'sam', 'password': 'pw-for-tests'}).status_code == 403


def test_students_cannot_use_teacher_endpoints(app_db):
    app, db = app_db
    sam = Api(app, 'sam')
    for method, path in [('get', '/problems'), ('post', '/quizzes'), ('get', '/students'), ('get', '/review'),
                         ('post', '/messages'), ('get', '/attempts/1')]:
        r = sam.call(method, path, json={})
        assert r.status_code == 403, (method, path, r.status_code)


def test_old_v1_is_locked(app_db):
    app, db = app_db
    c = app.test_client()
    for path in ('/api/v1/users', '/api/v1/files', '/api/v1/dieroll'):
        assert c.get(path).status_code == 401, path
    sam = Api(app, 'sam')
    assert c.get('/api/v1/users', headers={'Authorization': 'Bearer ' + sam.token}).status_code == 403
    teach = Api(app, 'teach')
    r = c.get('/api/v1/users', headers={'Authorization': 'Bearer ' + teach.token})
    assert r.status_code == 200 and {u['username'] for u in r.get_json()} == {'teach', 'sam', 'kim'}
    assert c.get('/api/v1/files', headers={'Authorization': 'Bearer ' + teach.token}).status_code == 200


# ---------------------------------------------------------------- a whole quiz through the API

def test_student_and_teacher_round_trip(app_db):
    app, db = app_db
    t, sam, kim = Api(app, 'teach'), Api(app, 'sam'), Api(app, 'kim')
    qid, pids = make_quiz(t)
    st = student_ids(db)
    r = t.post('/quizzes/{}/assign'.format(qid), json={'students': [st['sam'], st['kim']]})
    assert r.status_code == 201 and len(r.get_json()['assigned']) == 2

    mine = sam.get('/my/quizzes').get_json()['quizzes']
    assert len(mine) == 1 and mine[0]['attempts'][0]['status'] == 'open'
    aid = mine[0]['attempts'][0]['id']
    kim_aid = kim.get('/my/quizzes').get_json()['quizzes'][0]['attempts'][0]['id']
    assert sam.get('/my/attempts/{}'.format(kim_aid)).status_code == 404  # someone else's

    quiz = sam.get('/my/attempts/{}'.format(aid)).get_json()
    assert quiz['started'] and len(quiz['questions']) == 4
    # nothing in the student's copy gives the answers away
    text = json.dumps(quiz)
    assert 'correct' not in text and 'Mentions inertia' not in text and 'grading_notes' not in text

    # work out perfect answers from the teacher's view
    full = t.get('/attempts/{}'.format(aid)).get_json()
    right = {}
    for it in full['items']:
        n = str(it['number'])
        if it['type'] == 'numeric':
            right[n] = it['correct_answer']
        elif it['type'] == 'choice_one':
            right[n] = str(it['choices'].index(it['correct_answer']))
        elif it['type'] == 'choice_many':
            right[n] = [str(it['choices'].index(c)) for c in it['correct_answer'].split('; ')]
        else:
            right[n] = 'Because of inertia.'

    # bad answers are refused clearly
    many = [q for q in quiz['questions'] if q['type'] == 'choice_many'][0]
    r = sam.put('/my/attempts/{}/answers'.format(aid), json={'answers': {str(many['number']): '0'}})
    assert r.status_code == 400 and 'list of choice ids' in r.get_json()['error']['message']
    assert sam.put('/my/attempts/{}/answers'.format(aid), json={'answers': {'99': 'x'}}).status_code == 400
    # autosave, and it comes back
    assert sam.put('/my/attempts/{}/answers'.format(aid), json={'answers': right}).get_json()['saved']
    again = sam.get('/my/attempts/{}'.format(aid)).get_json()
    assert {str(q['number']): q['saved_answer'] for q in again['questions']} == right

    r = sam.post('/my/attempts/{}/submit'.format(aid))
    assert r.get_json()['status'] == 'review'  # the essay needs a teacher
    assert sam.get('/my/attempts/{}/results'.format(aid)).status_code == 409
    assert sam.post('/my/attempts/{}/submit'.format(aid)).status_code == 409

    # the teacher grades the essay
    waiting = t.get('/review').get_json()['waiting']
    assert [w['id'] for w in waiting] == [aid]
    essay_id = [it['id'] for it in full['items'] if it['type'] == 'essay'][0]
    r = t.post('/review/{}'.format(aid), json={'grades': {}, 'finish': True})
    assert r.status_code == 422
    r = t.post('/review/{}'.format(aid), json={'grades': {str(essay_id): {'credit': 50, 'feedback': 'Say more.',
                                                                           'highlights': [[0, 7, 'right']]}}, 'finish': True})
    assert r.status_code == 200 and r.get_json()['score'] == 100 * 3.5 / 4
    res = sam.get('/my/attempts/{}/results'.format(aid)).get_json()
    assert res['answers_shown'] and all('correct_answer' in it for it in res['items'])
    essay = [it for it in res['items'] if it['type'] == 'essay'][0]
    assert essay['feedback'] == 'Say more.' and essay['highlights'] == [{'start': 0, 'end': 7, 'kind': 'right'}]

    # kim hands in nothing: scored straight away, no teacher needed
    r = kim.post('/my/attempts/{}/submit'.format(kim_aid), json={'answers': {}})
    assert r.get_json()['status'] == 'completed' and r.get_json()['results']['attempt']['score'] == 0

    # retake, scoring rule, results by student
    new = t.post('/attempts/{}/retake'.format(aid)).get_json()
    assert new['status'] == 'open'
    t.put('/attempts/{}/scoring-rule'.format(aid), json={'rule': 'average'})
    grp = t.get('/students/{}/results'.format(st['sam'])).get_json()['quizzes'][0]
    assert grp['rule_overridden'] and grp['scoring_rule'] == 'average' and len(grp['attempts']) == 2
    assert t.put('/attempts/{}/scoring-rule'.format(aid), json={'rule': 'bogus'}).status_code == 400


def test_quiz_finished_and_scored_without_teacher(app_db):
    app, db = app_db
    t, sam = Api(app, 'teach'), Api(app, 'sam')
    r = t.post('/problems', json={'type': 'numeric', 'title': 'Add', 'question': '[a] + 1 = ?', 'answer': 'a + 1',
                                  'options': {'values': [A]}})
    qid = t.post('/quizzes', json={'title': 'Auto', 'problems': [r.get_json()['id']]}).get_json()['id']
    t.post('/quizzes/{}/assign'.format(qid), json={'students': [student_ids(db)['sam']]})
    aid = sam.get('/my/quizzes').get_json()['quizzes'][0]['attempts'][0]['id']
    q = sam.get('/my/attempts/{}'.format(aid)).get_json()['questions'][0]
    a = int(q['text'].split(' ')[0]) + 1
    r = sam.post('/my/attempts/{}/submit'.format(aid), json={'answers': {'1': str(a)}})
    assert r.get_json()['status'] == 'completed' and r.get_json()['results']['attempt']['score'] == 100
    assert t.get('/review').get_json()['waiting'] == []


def test_hidden_answers_and_windows(app_db):
    app, db = app_db
    from app.qgen.models import CQuiz
    t, sam = Api(app, 'teach'), Api(app, 'sam')
    qid, _ = make_quiz(t, hide_answers=True)
    later = datetime.now() + timedelta(days=1)
    r = t.post('/quizzes/{}/assign'.format(qid), json={'students': [student_ids(db)['sam']],
                                                        'opens_at': later.isoformat(timespec='minutes')})
    aid = r.get_json()['assigned'][0]['id']
    r = sam.get('/my/attempts/{}'.format(aid))
    assert r.status_code == 409 and r.get_json()['error']['code'] == 'not_open'
    cq = db.session.get(CQuiz, aid)
    cq.opens_at = None
    db.session.commit()
    sam.get('/my/attempts/{}'.format(aid))
    sam.post('/my/attempts/{}/submit'.format(aid))  # all blank, essay too: scored at once
    res = sam.get('/my/attempts/{}/results'.format(aid)).get_json()
    assert res['answers_shown'] is False and not any('correct_answer' in it for it in res['items'])
    t.post('/quizzes/{}/release'.format(qid), json={'released': True})
    assert sam.get('/my/attempts/{}/results'.format(aid)).get_json()['answers_shown'] is True
    bad = t.post('/quizzes/{}/assign'.format(qid), json={'students': [student_ids(db)['kim']], 'opens_at': 'soon'})
    assert bad.status_code == 400


def test_overdue_quizzes_close_on_their_own(app_db):
    app, db = app_db
    from app.qgen import services as S
    from app.qgen.models import CQuiz
    t, sam = Api(app, 'teach'), Api(app, 'sam')
    r = t.post('/problems', json={'type': 'numeric', 'title': 'Add', 'question': '[a] + 1 = ?', 'answer': 'a + 1',
                                  'options': {'values': [A]}})
    qid = t.post('/quizzes', json={'title': 'Timed', 'problems': [r.get_json()['id']]}).get_json()['id']
    st = student_ids(db)
    t.post('/quizzes/{}/assign'.format(qid), json={'students': [st['sam'], st['kim']], 'time_limit_minutes': 10})
    sam_q = CQuiz.query.filter_by(assignee=st['sam']).one()
    kim_q = CQuiz.query.filter_by(assignee=st['kim']).one()
    aid = sam_q.id
    sam.get('/my/attempts/{}'.format(aid))
    sam.put('/my/attempts/{}/answers'.format(aid), json={'answers': {'1': '999'}})
    # sam walks away; time passes; nobody opens anything
    sam_q.startdate = datetime.now() - timedelta(minutes=30)
    kim_q.closes_at = datetime.now() - timedelta(minutes=5)
    db.session.commit()
    assert S.close_expired() == 2
    db.session.expire_all()
    assert db.session.get(CQuiz, aid).completed and db.session.get(CQuiz, aid).score == 0
    assert db.session.get(CQuiz, kim_q.id).completed
    assert S.close_expired() == 0


# ---------------------------------------------------------------- teacher checks

def test_problem_checks_and_protection(app_db):
    app, db = app_db
    t = Api(app, 'teach')
    r = t.post('/problems', json={'type': 'numeric', 'title': 'Bad', 'question': '[a] + [hrs]', 'answer': 'a',
                                  'options': {'values': [A]}})
    assert r.status_code == 422 and any('hrs' in e for e in r.get_json()['error']['details'])
    assert t.post('/problems', json={'type': 'nope', 'title': 'x', 'question': 'q'}).status_code == 400
    assert t.post('/problems', json={'title': 'x', 'question': 'q', 'options': {'colour': 'red'}}).status_code == 400
    assert t.post('/problems', json={'title': 'x', 'question': 'q', 'options': {'show_n': 'three'}}).status_code == 400
    r = t.post('/problems/preview', json={'type': 'numeric', 'question': '[a] + 1', 'answer': 'a + 1', 'options': {'values': [A]}})
    assert len(r.get_json()['samples']) == 3
    qid, pids = make_quiz(t)
    assert t.delete('/problems/{}'.format(pids[0])).status_code == 409
    got = t.get('/problems/{}'.format(pids[0])).get_json()
    assert got['answer'] == 'a + b' and got['options']['values'][0]['name'] == 'a'
    upd = dict(title='Add v2', question='[a] + [b] + 1 = ?', answer='a + b + 1', type='numeric', options={'values': [A, B]})
    assert t.put('/problems/{}'.format(pids[0]), json=upd).get_json()['title'] == 'Add v2'
    assert t.get('/problems/99999').status_code == 404
    # groups in quizzes, and bad groups
    r = t.post('/quizzes', json={'title': 'G', 'problems': [pids[0], {'pick': 2, 'from': pids[1:]}]})
    assert r.status_code == 201 and r.get_json()['questions_per_student'] == 3
    r = t.post('/quizzes', json={'title': 'G2', 'problems': [{'pick': 9, 'from': pids[1:]}]})
    assert r.status_code == 422
    assert t.post('/quizzes', json={'title': 'G3', 'problems': [424242]}).status_code == 422
    t.post('/quizzes/{}/assign'.format(qid), json={'students': [student_ids(db)['sam']]})
    assert t.delete('/quizzes/{}'.format(qid)).status_code == 409
    assert t.post('/quizzes/{}/assign'.format(qid), json={'students': [123456]}).status_code == 400


def test_messages_through_the_api(app_db):
    app, db = app_db
    t, sam, kim = Api(app, 'teach'), Api(app, 'sam'), Api(app, 'kim')
    st = student_ids(db)
    assert t.post('/messages', json={'to': [st['sam'], st['kim']], 'body': 'Test Friday!', 'pin': True}).status_code == 201
    got = sam.get('/my/messages').get_json()
    assert got['pinned'][0]['body'] == 'Test Friday!' and got['unread_before'] == 1
    assert sam.post('/my/messages', json={'body': 'OK!'}).status_code == 201
    inbox = t.get('/messages').get_json()
    assert [c for c in inbox['conversations'] if c['student']['id'] == st['sam']][0]['unread'] == 1
    assert len(inbox['pinned']) == 1  # one entry for the whole broadcast
    mid = inbox['pinned'][0]['id']
    assert t.put('/messages/pin/{}'.format(mid), json={'pinned': False}).get_json()['updated'] == 2
    assert kim.get('/my/messages').get_json()['pinned'] == []
    assert t.post('/messages', json={'to': [st['sam'], 1], 'body': 'x'}).status_code == 422  # 1 is the teacher
    assert t.post('/messages', json={'to': 'all', 'body': ''}).status_code == 422
    assert t.get('/messages/{}'.format(st['sam'])).get_json()['messages'][-1]['body'] == 'OK!'


# ---------------------------------------------------------------- the description stays true

def test_every_route_is_documented(app_db):
    app, db = app_db
    from app.api.docs import ENDPOINTS
    documented = {(m, '/api/v2' + p.replace('{', '<').replace('}', '>')) for m, p, *_ in ENDPOINTS}
    actual = set()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith('/api/v2'):
            path = rule.rule
            for conv in ('int:',):
                path = path.replace('<' + conv, '<')
            for m in rule.methods - {'HEAD', 'OPTIONS'}:
                actual.add((m, path))
    # names of path parts may differ; compare shapes
    shape = lambda s: {(m, '/'.join('<>' if part.startswith('<') else part for part in p.split('/'))) for m, p in s}
    assert shape(actual) == shape(documented)
    spec = Api(app).get('/openapi.json').get_json()
    assert spec['openapi'].startswith('3.1') and '/my/quizzes' in spec['paths']
    assert b'API for apps' in app.test_client().get('/api/v2/docs').data


def test_retake_only_after_finishing(app_db):
    app, db = app_db
    t = Api(app, 'teach')
    r = t.post('/problems', json={'type': 'numeric', 'title': 'Add', 'question': '[a] + 1 = ?', 'answer': 'a + 1',
                                  'options': {'values': [A]}})
    qid = t.post('/quizzes', json={'title': 'R', 'problems': [r.get_json()['id']]}).get_json()['id']
    aid = t.post('/quizzes/{}/assign'.format(qid), json={'students': [student_ids(db)['sam']]}).get_json()['assigned'][0]['id']
    r = t.post('/attempts/{}/retake'.format(aid))
    assert r.status_code == 409 and "hasn't finished" in r.get_json()['error']['message']
