"""A signed-in user's own quizzes and messages ("my"): what a student app needs."""
from flask import g, jsonify, request

from app import db
from app.messages import services as M
from app.messages.routes import student_panel
from app.qgen import services as S
from app.qgen.models import CQuiz, ArchivedAttempt
from app.qgen.qtypes import get_qtype
from . import api_bp
from .auth import token_required, body
from app import tuning
from .errors import ApiError, bad_request, not_found, conflict
from .serialize import (my_quizzes_json, attempt_json, attempt_summary, results_json, message_json)



def my_attempt(attempt_id):
    cq = db.session.get(CQuiz, attempt_id)
    if not cq and ArchivedAttempt.query.filter_by(original_id=attempt_id, student_id=g.api_user.id).first():
        raise ApiError(410, 'removed', 'Your teacher has removed this quiz attempt.')
    if not cq or cq.assignee != g.api_user.id:
        raise not_found('That quiz')
    return cq


def clean_answers(cq, answers):
    """Check an app's answers {question number: answer} against this attempt's questions."""
    if not isinstance(answers, dict):
        raise bad_request('"answers" must be an object like {"1": "42", "2": "0", "3": ["0", "2"]}.')
    by_number = {cp.ordinal: cp for cp in cq.cproblems}
    out = {}
    for key, value in answers.items():
        try:
            number = int(key)
        except (TypeError, ValueError):
            raise bad_request('"{}" isn\'t a question number.'.format(key))
        cp = by_number.get(number)
        if not cp:
            raise bad_request('This quiz has no question {}.'.format(number))
        qt = get_qtype(cp.vproblem.qtype)
        ids = [str(i) for i in range(len(cp.conc_opts.get('choices', [])))]
        if value is None:
            out[number] = None
        elif 'choices' in cp.conc_opts and qt.multi:
            if not isinstance(value, list) or not all(str(v) in ids for v in value):
                raise bad_request('Question {} takes a list of choice ids from {}.'.format(number, ids))
            out[number] = [str(v) for v in value]
        elif 'choices' in cp.conc_opts:
            if str(value) not in ids:
                raise bad_request('Question {} takes one choice id from {}.'.format(number, ids))
            out[number] = str(value)
        else:
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise bad_request('Question {} takes text.'.format(number))
            text = str(value)
            if len(text) > tuning.get('max_api_answer'):
                raise bad_request('The answer to question {} is too long.'.format(number))
            out[number] = text
    return out


@api_bp.route('/my/quizzes', methods=['GET'])
@token_required()
def my_quizzes():
    from app.qgen.models import mark_quizzes_seen
    mark_quizzes_seen(g.api_user.id)  # like opening My quizzes on the site
    return jsonify(quizzes=my_quizzes_json(g.api_user))


@api_bp.route('/my/attempts/<int:attempt_id>', methods=['GET'])
@token_required()
def open_attempt(attempt_id):
    """Open a quiz to take it (starts the time limit), or see where it stands."""
    cq = my_attempt(attempt_id)
    state = S.attempt_state(cq)
    if state == 'time_up':
        S.submit(cq)
        state = S.attempt_state(cq)
    if state == 'not_open':
        raise ApiError(409, 'not_open', 'You can\'t start this quiz yet. It opens {}.'.format(cq.opens_at.isoformat(timespec='minutes')),
                       {'opens_at': cq.opens_at.isoformat(timespec='seconds')})
    if state == 'open':
        S.start(cq)
        return jsonify(attempt_json(cq))
    if state == 'completed':
        return jsonify(results_json(cq))
    return jsonify({'attempt': attempt_summary(cq)})


@api_bp.route('/my/attempts/<int:attempt_id>/answers', methods=['PUT'])
@token_required()
def save_answers(attempt_id):
    """Autosave: {"answers": {"1": "42", ...}}. Only the questions sent are changed."""
    cq = my_attempt(attempt_id)
    answers = clean_answers(cq, body(required=('answers',))['answers'])
    try:
        S.autosave(cq, answers)
    except S.ServiceError as exc:
        raise conflict(str(exc))
    return jsonify(saved=True, attempt=attempt_summary(cq))


@api_bp.route('/my/attempts/<int:attempt_id>/submit', methods=['POST'])
@token_required()
def submit_attempt(attempt_id):
    """Hand in. Optional {"answers": {...}}; questions not sent keep their saved answer."""
    cq = my_attempt(attempt_id)
    #the body is optional here: no body means "hand in what's saved"
    data = body() if request.get_data() else {}
    answers = clean_answers(cq, data['answers']) if 'answers' in data else None
    if S.attempt_state(cq) == 'time_up':
        answers = None  # too late for new answers; the saved ones count
    try:
        status = S.submit(cq, answers)
    except S.ServiceError as exc:
        raise conflict(str(exc))
    out = {'status': status, 'attempt': attempt_summary(cq)}
    if status == 'completed':
        out['results'] = results_json(cq)
    return jsonify(out)


@api_bp.route('/my/attempts/<int:attempt_id>/results', methods=['GET'])
@token_required()
def my_results(attempt_id):
    cq = my_attempt(attempt_id)
    if not cq.completed:
        raise conflict('Results appear once the quiz is submitted{}.'.format(' and graded' if cq.needs_review else ''))
    return jsonify(results_json(cq))


@api_bp.route('/my/messages', methods=['GET'])
@token_required()
def my_messages():
    """A student's conversation with the teachers (reading marks the messages seen)."""
    if g.api_user.is_admin:
        raise ApiError(403, 'forbidden', 'Teachers use /messages.')
    panel = student_panel(g.api_user)
    return jsonify(pinned=[message_json(m) for m in panel['pinned']],
                   messages=[message_json(m) for m in M.thread(g.api_user.id)],
                   unread_before=len(panel['unread_ids']),
                   #who "to" can name when writing (online ones first)
                   teachers=[{'id': t['teacher'].id, 'username': t['teacher'].username, 'nickname': t['teacher'].nickname, 'online': t['online']}
                             for t in panel['teachers']])


@api_bp.route('/my/messages', methods=['POST'])
@token_required()
def my_reply():
    try:
        data = body(required=('body',))
        #"to": a teacher's id or a list of them (only they see it), or "all"/left out for every teacher
        M.reply(g.api_user, data['body'], data.get('to'))
    except M.MessageError as exc:
        raise ApiError(422, 'invalid', str(exc))
    return jsonify(sent=True), 201
