"""What a teacher app needs: problems, quizzes, assigning, results, grading, messages."""
from datetime import datetime

from flask import g, jsonify

from app import db
from app.messages import services as M
from app.qgen import services as S
from app.qgen.models import CQuiz, VQuiz, VProblem, RETAKE_RULES
from app.qgen.qtypes import REGISTRY, PRECISIONS
from app.user.models import User
from . import api_bp
from .auth import token_required, body
from .errors import ApiError, bad_request, not_found, conflict, invalid
from .serialize import (problem_json, vquiz_json, teacher_attempt_json, attempt_summary, student_results_json,
                        user_json, message_json)

teacher = token_required(teacher=True)

#problem settings an app may send, with their defaults
OPTION_DEFAULTS = {'values': [], 'choices': '', 'combos': '', 'shuffle': True, 'show_n': None,
                   'case_sensitive': False, 'precision': 'close', 'complex': False, 'grading_notes': '',
                   'images': []}
VALUE_KEYS = ('name', 'kind', 'min', 'max', 'step', 'places', 'nonzero', 'items', 'pick_n', 'formula',
              'im_min', 'im_max', 'different_from')


def get_or_404(model, ident, what):
    row = db.session.get(model, ident)
    if not row:
        raise not_found(what)
    return row


def problem_input(data):
    """Check the shape of a problem sent by an app -> (qtype, title, question, answer, options, calculator_ok)."""
    qtype = data.get('type', 'numeric')
    if qtype not in REGISTRY:
        raise bad_request('"type" must be one of: {}.'.format(', '.join(REGISTRY)))
    for key in ('title', 'question', 'answer'):
        if data.get(key) is not None and not isinstance(data[key], str):
            raise bad_request('"{}" must be text.'.format(key))
    options = dict(OPTION_DEFAULTS)
    given = data.get('options') or {}
    if not isinstance(given, dict):
        raise bad_request('"options" must be an object.')
    unknown = sorted(set(given) - set(OPTION_DEFAULTS))
    if unknown:
        raise bad_request('Unknown options: {}. Allowed: {}.'.format(', '.join(unknown), ', '.join(OPTION_DEFAULTS)))
    options.update(given)
    values = []
    if not isinstance(options['values'], list):
        raise bad_request('"options.values" must be a list.')
    for row in options['values']:
        if not isinstance(row, dict) or set(row) - set(VALUE_KEYS):
            raise bad_request('Each value is an object with keys from: {}.'.format(', '.join(VALUE_KEYS)))
        clean = {}
        for k, v in row.items():
            if k == 'nonzero':
                clean[k] = bool(v)
            elif k == 'different_from':
                if not isinstance(v, list):
                    raise bad_request('"different_from" must be a list of names.')
                clean[k] = [str(x) for x in v]
            elif v is not None:
                clean[k] = str(v)
        values.append(clean)
    options['values'] = values
    if options['show_n'] is not None and (not isinstance(options['show_n'], int) or isinstance(options['show_n'], bool)):
        raise bad_request('"options.show_n" must be a whole number or null.')
    if options['precision'] not in PRECISIONS:
        raise bad_request('"options.precision" must be one of: {}.'.format(', '.join(PRECISIONS)))
    if not isinstance(options['images'], list) or not all(isinstance(i, dict) and 'file' in i for i in options['images']):
        raise bad_request('"options.images" must be a list of {"file": ..., "label": ...}.')
    options['images'] = [{'file': str(i['file']), 'label': str(i.get('label') or '')} for i in options['images']]
    for key in ('choices', 'combos', 'grading_notes'):
        options[key] = str(options[key] or '')
    for key in ('shuffle', 'case_sensitive', 'complex'):
        options[key] = bool(options[key])
    question = data.get('question') or ''
    options['markup'] = 'legacy' if '{{' in question else 'friendly'
    return qtype, data.get('title') or '', question, data.get('answer') or '', options, bool(data.get('calculator_ok'))


# ---------------------------------------------------------------- problems

@api_bp.route('/problems', methods=['GET'])
@teacher
def list_problems():
    return jsonify(problems=[problem_json(p) for p in VProblem.query.order_by(VProblem.id.desc()).all()])


@api_bp.route('/problems', methods=['POST'])
@teacher
def create_problem():
    qtype, title, question, answer, options, calc = problem_input(body(required=('title', 'question')))
    vp = VProblem(author_id=g.api_user.id)
    errors = S.save_problem(vp, qtype, title, question, answer, options, calc)
    if errors:
        db.session.rollback()
        raise invalid(errors)
    return jsonify(problem_json(vp, full=True)), 201


@api_bp.route('/problems/preview', methods=['POST'])
@teacher
def preview_problem():
    """Three sample versions without saving; the same as "Show me 3 examples"."""
    qtype, title, question, answer, options, calc = problem_input(body(required=('question',)))
    errors, samples = S.preview_problem(qtype, question, answer, options)
    if errors:
        raise invalid(errors)
    return jsonify(samples=samples)


@api_bp.route('/problems/<int:pid>', methods=['GET'])
@teacher
def get_problem(pid):
    return jsonify(problem_json(get_or_404(VProblem, pid, 'That problem'), full=True))


@api_bp.route('/problems/<int:pid>', methods=['PUT'])
@teacher
def update_problem(pid):
    vp = get_or_404(VProblem, pid, 'That problem')
    qtype, title, question, answer, options, calc = problem_input(body(required=('title', 'question')))
    errors = S.save_problem(vp, qtype, title, question, answer, options, calc)
    if errors:
        db.session.rollback()
        raise invalid(errors)
    return jsonify(problem_json(vp, full=True))


@api_bp.route('/problems/<int:pid>', methods=['DELETE'])
@teacher
def delete_problem(pid):
    try:
        S.delete_problem(get_or_404(VProblem, pid, 'That problem'))
    except S.ServiceError as exc:
        raise conflict(str(exc))
    return '', 204


# ---------------------------------------------------------------- quizzes

def quiz_settings(data):
    settings = {}
    for key in ('calculator_ok', 'shuffle_order', 'hide_answers'):
        if key in data:
            settings[key] = bool(data[key])
    if 'retake_rule' in data:
        if data['retake_rule'] not in RETAKE_RULES:
            raise bad_request('"retake_rule" must be one of: {}.'.format(', '.join(RETAKE_RULES)))
        settings['retake_rule'] = data['retake_rule']
    if 'image' in data:
        settings['image'] = str(data['image']) if data['image'] else None
    return settings


@api_bp.route('/quizzes', methods=['GET'])
@teacher
def list_vquizzes():
    return jsonify(quizzes=[vquiz_json(q) for q in VQuiz.query.order_by(VQuiz.id.desc()).all()])


@api_bp.route('/quizzes', methods=['POST'])
@teacher
def create_vquiz():
    """{title, problems: [4, {"pick": 2, "from": [5, 6, 7]}], calculator_ok?, shuffle_order?, retake_rule?, hide_answers?, image?}"""
    data = body(required=('title', 'problems'))
    vq = VQuiz()
    errors = S.save_vquiz(vq, str(data['title']), data['problems'], author_id=g.api_user.id, **quiz_settings(data))
    if errors:
        db.session.rollback()
        raise invalid(errors)
    return jsonify(vquiz_json(vq, full=True)), 201


@api_bp.route('/quizzes/<int:qid>', methods=['GET'])
@teacher
def get_vquiz(qid):
    return jsonify(vquiz_json(get_or_404(VQuiz, qid, 'That quiz'), full=True))


@api_bp.route('/quizzes/<int:qid>', methods=['PUT'])
@teacher
def update_vquiz(qid):
    vq = get_or_404(VQuiz, qid, 'That quiz')
    data = body(required=('title', 'problems'))
    errors = S.save_vquiz(vq, str(data['title']), data['problems'], **quiz_settings(data))
    if errors:
        db.session.rollback()
        raise invalid(errors)
    return jsonify(vquiz_json(vq, full=True))


@api_bp.route('/quizzes/<int:qid>', methods=['DELETE'])
@teacher
def delete_vquiz(qid):
    try:
        S.delete_vquiz(get_or_404(VQuiz, qid, 'That quiz'))
    except S.ServiceError as exc:
        raise conflict(str(exc))
    return '', 204


@api_bp.route('/quizzes/<int:qid>/release', methods=['POST'])
@teacher
def release_vquiz(qid):
    """{"released": true} shows correct answers to students who have finished; false hides them again."""
    vq = get_or_404(VQuiz, qid, 'That quiz')
    S.release_answers(vq, bool(body(required=('released',))['released']))
    return jsonify(vquiz_json(vq))


def parse_when(data, key):
    if not data.get(key):
        return None
    try:
        return datetime.fromisoformat(str(data[key]))
    except ValueError:
        raise bad_request('"{}" must be a date and time like 2026-10-05T09:00.'.format(key))


@api_bp.route('/quizzes/<int:qid>/assign', methods=['POST'])
@teacher
def assign_vquiz(qid):
    """{"students": [ids], "opens_at"?, "closes_at"?, "time_limit_minutes"?} -> each student's own copy."""
    vq = get_or_404(VQuiz, qid, 'That quiz')
    data = body(required=('students',))
    ids = data['students']
    if not isinstance(ids, list) or not ids:
        raise bad_request('"students" must be a list of student ids.')
    students = User.query.filter(User.id.in_([int(i) for i in ids if str(i).isdigit()])).all()
    if len(students) != len(set(ids)):
        raise bad_request('Some of those student ids don\'t exist.')
    limit = data.get('time_limit_minutes')
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool)):
        raise bad_request('"time_limit_minutes" must be a whole number.')
    try:
        created, failed = S.assign(vq, students, parse_when(data, 'opens_at'), parse_when(data, 'closes_at'), limit)
    except S.ServiceError as exc:
        raise invalid([str(exc)])
    return jsonify(assigned=[attempt_summary(cq) | {'student_id': cq.assignee} for cq in created],
                   failed=[{'student_id': u.id, 'error': err} for u, err in failed]), 201


# ---------------------------------------------------------------- students and attempts

@api_bp.route('/students', methods=['GET'])
@teacher
def list_students():
    return jsonify(students=[user_json(u, full=True) for u in User.query.filter_by(is_admin=False).order_by(User.username)])


@api_bp.route('/students/<int:uid>/results', methods=['GET'])
@teacher
def student_results(uid):
    u = get_or_404(User, uid, 'That student')
    return jsonify(student=user_json(u, full=True), quizzes=student_results_json(u))


@api_bp.route('/attempts/<int:aid>', methods=['GET'])
@teacher
def get_attempt(aid):
    return jsonify(teacher_attempt_json(get_or_404(CQuiz, aid, 'That attempt')))


@api_bp.route('/attempts/<int:aid>', methods=['DELETE'])
@teacher
def delete_attempt(aid):
    S.delete_attempt(get_or_404(CQuiz, aid, 'That attempt'))
    return '', 204


@api_bp.route('/attempts/<int:aid>/retake', methods=['POST'])
@teacher
def retake(aid):
    try:
        new = S.retake(get_or_404(CQuiz, aid, 'That attempt'))
    except S.ServiceError as exc:
        raise conflict(str(exc))
    return jsonify(attempt_summary(new)), 201


@api_bp.route('/attempts/<int:aid>/scoring-rule', methods=['PUT'])
@teacher
def scoring_rule(aid):
    """{"rule": "average"} for this student and quiz, or {"rule": null} to use the quiz's rule."""
    cq = get_or_404(CQuiz, aid, 'That attempt')
    try:
        S.set_retake_rule(cq, body(required=('rule',))['rule'])
    except S.ServiceError as exc:
        raise bad_request(str(exc))
    return jsonify(student_results_json(cq.taker))


# ---------------------------------------------------------------- grading

@api_bp.route('/review', methods=['GET'])
@teacher
def review_list():
    waiting = CQuiz.query.filter_by(needs_review=True, completed=False).order_by(CQuiz.compdate).all()
    return jsonify(waiting=[attempt_summary(cq) | {'student': user_json(cq.taker)} for cq in waiting])


@api_bp.route('/review/<int:aid>', methods=['POST'])
@teacher
def grade(aid):
    """{"grades": {"<answer id>": {"credit": 0-100, "feedback": "...", "highlights": [[start, end, "right"|"wrong"]]}},
        "finish": true} -- finishing needs a credit for every written answer."""
    cq = get_or_404(CQuiz, aid, 'That attempt')
    data = body(required=('grades',))
    if not isinstance(data['grades'], dict):
        raise bad_request('"grades" must be an object keyed by answer id.')
    try:
        ungraded = S.grade_essays(cq, data['grades'], finish=bool(data.get('finish')), grader_id=g.api_user.id)
    except S.ServiceError as exc:
        raise conflict(str(exc))
    except (ValueError, TypeError):
        db.session.rollback()
        raise bad_request('Credits must be numbers from 0 to 100, and answer ids whole numbers.')
    if ungraded:
        raise invalid(['Give a credit for question{} {} before finishing.'.format('s' if len(ungraded) > 1 else '', ', '.join(map(str, ungraded)))])
    return jsonify(teacher_attempt_json(cq))


# ---------------------------------------------------------------- messages

@api_bp.route('/messages', methods=['GET'])
@teacher
def inbox():
    return jsonify(conversations=[{'student': user_json(r['student']), 'unread': r['unread'],
                                   'last': message_json(r['last']) if r['last'] else None} for r in M.inbox()],
                   pinned=[message_json(m) for m in M.pinned_announcements()])


@api_bp.route('/messages/<int:student_id>', methods=['GET'])
@teacher
def conversation(student_id):
    student = get_or_404(User, student_id, 'That student')
    items = M.thread(student.id)
    M.mark_seen_by_teachers(student.id)
    return jsonify(student=user_json(student), messages=[message_json(m) for m in items])


@api_bp.route('/messages', methods=['POST'])
@teacher
def send_message():
    """{"to": "all" | student id | [ids], "body": "...", "pin"?: true}"""
    data = body(required=('to', 'body'))
    try:
        students = M.send(g.api_user, data['to'], data['body'], pinned=bool(data.get('pin')))
    except M.MessageError as exc:
        raise ApiError(422, 'invalid', str(exc))
    return jsonify(sent_to=[s.id for s in students]), 201


@api_bp.route('/messages/pin/<int:message_id>', methods=['PUT'])
@teacher
def pin_message(message_id):
    """{"pinned": true|false}: also applies to every copy sent with it."""
    from app.messages.models import Message
    msg = get_or_404(Message, message_id, 'That message')
    count = M.set_pinned(msg, bool(body(required=('pinned',))['pinned']))
    return jsonify(updated=count)

