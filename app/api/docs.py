"""The API's description: /api/v2/openapi.json for tools, /api/v2/docs for people.
Both come from ENDPOINTS below, so they can't disagree. When you add an
endpoint, add a line here too (tests/test_api.py checks that every route is listed)."""
from flask import jsonify, render_template

from . import api_bp

#(method, path, who, summary, example request body or None)
ENDPOINTS = [
    ('POST', '/tokens', 'anyone', 'Sign in: get a personal access token (shown once).',
     {'username': 'sam', 'password': '…', 'name': "Sam's phone", 'days': 90}),
    ('GET', '/tokens', 'signed in', 'Your tokens (without the secret part).', None),
    ('DELETE', '/tokens/{token_id}', 'signed in', 'Revoke one of your tokens.', None),
    ('DELETE', '/tokens/current', 'signed in', 'Sign out: revoke the token used for this request.', None),
    ('GET', '/me', 'signed in', 'Who you are.', None),
    ('POST', '/me/avatar', 'signed in', 'Upload your picture (multipart/form-data, field "file"); cropped to a square.', None),
    ('DELETE', '/me/avatar', 'signed in', 'Remove your picture.', None),

    ('GET', '/my/quizzes', 'signed in', 'Your quizzes, grouped with retakes, and the score that counts.', None),
    ('GET', '/my/attempts/{attempt_id}', 'signed in', 'Open a quiz to take it (starts any time limit), or see its results.', None),
    ('PUT', '/my/attempts/{attempt_id}/answers', 'signed in', 'Autosave answers so far. Choices are ids; several choices a list.',
     {'answers': {'1': '42', '2': '0', '3': ['0', '2'], '4': '3 + 2i'}}),
    ('POST', '/my/attempts/{attempt_id}/submit', 'signed in', 'Hand in (optionally with final answers).', {'answers': {'1': '42'}}),
    ('GET', '/my/attempts/{attempt_id}/results', 'signed in', 'Your results (correct answers only once the teacher allows).', None),
    ('GET', '/my/messages', 'student', 'Your messages and pinned announcements (reading marks them seen), and your teachers (online ones first).', None),
    ('POST', '/my/messages', 'student', 'Write to all your teachers, or to some ("to": a teacher\'s id or a list of ids; only they see it).',
     {'body': 'Can I retake quiz 2?', 'to': 'all'}),

    ('GET', '/problems', 'teacher', 'All problems.', None),
    ('POST', '/problems', 'teacher', 'Create a problem (checked like the web page; 422 lists what to fix).',
     {'type': 'numeric', 'title': 'Train', 'question': 'A train goes [speed] mph for [hours] hours. How far?',
      'answer': 'speed * hours', 'calculator_ok': False,
      'options': {'values': [{'name': 'speed', 'kind': 'whole', 'min': 40, 'max': 80, 'step': 5},
                             {'name': 'hours', 'kind': 'whole', 'min': 2, 'max': 5}]}}),
    ('POST', '/problems/preview', 'teacher', 'Three sample versions, without saving.', {'type': 'numeric', 'question': '[a] + 1', 'answer': 'a + 1',
                                                                                    'options': {'values': [{'name': 'a', 'kind': 'whole', 'min': 1, 'max': 9}]}}),
    ('GET', '/problems/{problem_id}', 'teacher', 'One problem, with its answer and settings.', None),
    ('PUT', '/problems/{problem_id}', 'teacher', 'Replace a problem (same body as creating).', None),
    ('DELETE', '/problems/{problem_id}', 'teacher', 'Delete a problem (409 if quizzes or student answers use it).', None),

    ('GET', '/quizzes', 'teacher', 'All quizzes.', None),
    ('POST', '/quizzes', 'teacher', 'Create a quiz. Problems are ids, or groups each student draws from.',
     {'title': 'Week 3', 'problems': [4, {'pick': 2, 'from': [5, 6, 7]}], 'shuffle_order': True,
      'retake_rule': 'best', 'hide_answers': False, 'calculator_ok': False}),
    ('GET', '/quizzes/{quiz_id}', 'teacher', 'One quiz. calculator_ok is its own setting; calculator_allowed is what students get (also true when any of its problems allows a calculator).', None),
    ('PUT', '/quizzes/{quiz_id}', 'teacher', 'Replace a quiz (same body as creating). A new retake_rule applies to every student, replacing any rule set for one student.', None),
    ('DELETE', '/quizzes/{quiz_id}', 'teacher', 'Delete a quiz (409 once it has been assigned).', None),
    ('POST', '/quizzes/{quiz_id}/release', 'teacher', 'Show (true) or hide (false) correct answers to students.', {'released': True}),
    ('POST', '/quizzes/{quiz_id}/assign', 'teacher', 'Give each student a separate random copy.',
     {'students': [7, 8], 'opens_at': '2026-10-05T09:00', 'closes_at': '2026-10-05T10:00', 'time_limit_minutes': 30}),

    ('GET', '/students', 'teacher', 'All students.', None),
    ('GET', '/students/{student_id}/results', 'teacher', "A student's quizzes, attempts and counted scores.", None),
    ('GET', '/attempts/{attempt_id}', 'teacher', 'One attempt in full: answers, correct answers, grading.', None),
    ('DELETE', '/attempts/{attempt_id}', 'teacher', 'Move an attempt to the archive (it can be viewed or restored later).', None),
    ('GET', '/archive', 'teacher', 'Deleted attempts, newest first (?label= a quiz label id, or none).', None),
    ('GET', '/archive/{archived_id}', 'teacher', 'One archived attempt, with its results page as HTML.', None),
    ('POST', '/archive/{archived_id}/restore', 'teacher', 'Put it back as it was (not if the student, quiz or a problem is gone).', None),
    ('DELETE', '/archive/{archived_id}', 'teacher', 'Delete an archived attempt for good.', None),
    ('POST', '/attempts/{attempt_id}/retake', 'teacher', 'Give the student a fresh copy with new values.', None),
    ('PUT', '/attempts/{attempt_id}/scoring-rule', 'teacher', "How this student's attempts combine (null = quiz's rule).", {'rule': 'average'}),

    ('GET', '/review', 'teacher', 'Attempts waiting for essay grading.', None),
    ('POST', '/review/{attempt_id}', 'teacher', 'Grade written answers; "finish" closes the quiz.',
     {'grades': {'123': {'credit': 80, 'feedback': 'Good, but say why.', 'highlights': [[0, 12, 'right']]}}, 'finish': True}),

    ('GET', '/messages', 'teacher', 'Every student conversation, unread first, plus pinned announcements.', None),
    ('GET', '/messages/{student_id}', 'teacher', "One student's conversation (reading marks it seen).", None),
    ('POST', '/messages', 'teacher', "Send to 'all', one student id, or a list; optionally pinned.", {'to': 'all', 'body': 'No class Friday.', 'pin': True}),
    ('PUT', '/messages/pin/{message_id}', 'teacher', 'Pin or unpin (with every copy sent together).', {'pinned': False}),

    ('GET', '/openapi.json', 'anyone', 'This description, in OpenAPI 3.1.', None),
    ('GET', '/docs', 'anyone', 'This description, as a page.', None),
]

ERROR_EXAMPLE = {'error': {'code': 'invalid', 'message': 'Please fix: …', 'details': ['…']}}


def openapi():
    paths = {}
    for method, path, who, summary, example in ENDPOINTS:
        op = {'summary': summary, 'description': 'Who: {}.'.format(who),
              'responses': {'200': {'description': 'OK'}, '4XX': {'description': 'Error',
                            'content': {'application/json': {'example': ERROR_EXAMPLE}}}}}
        if who != 'anyone':
            op['security'] = [{'bearer': []}]
        else:
            op['security'] = []
        params = [p.strip('{}') for p in path.split('/') if p.startswith('{')]
        if params:
            op['parameters'] = [{'name': p, 'in': 'path', 'required': True, 'schema': {'type': 'integer'}} for p in params]
        if example is not None:
            op['requestBody'] = {'content': {'application/json': {'example': example}}}
        paths.setdefault(path, {})[method.lower()] = op
    return {
        'openapi': '3.1.0',
        'info': {'title': 'Quizzes API', 'version': '2.0',
                 'description': 'Sign in with POST /tokens, then send "Authorization: Bearer <token>". '
                                'Errors are JSON: {"error": {"code", "message", "details"}}. '
                                'Dates are ISO 8601 in the server\'s local time.'},
        'servers': [{'url': '/api/v2'}],
        'components': {'securitySchemes': {'bearer': {'type': 'http', 'scheme': 'bearer',
                                                      'description': 'A personal access token starting with qg_'}}},
        'paths': paths,
    }


@api_bp.route('/openapi.json', methods=['GET'])
def openapi_json():
    return jsonify(openapi())


@api_bp.route('/docs', methods=['GET'])
def docs_page():
    return render_template('api_docs.html', endpoints=ENDPOINTS, title='API')
