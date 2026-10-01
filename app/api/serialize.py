"""How records look in API responses. Dates are ISO 8601 (local server time).

A student's view never includes correct answers before the attempt is
finished (and, when the teacher hides them, before they're released).
"""
from flask import url_for

from app.qgen.formfact import problem_image, transcript_item
from app.qgen.models import attempts_by_quiz
from app.qgen.qtypes import get_qtype
from app.qgen import layout
from app.qgen import services as S


def iso(dt):
    return dt.isoformat(timespec='seconds') if dt else None


def static_url(name):
    return url_for('static', filename=name, _external=True) if name else None


def user_json(u, full=False):
    out = {'id': u.id, 'username': u.username, 'is_teacher': bool(u.is_admin),
           'avatar_url': static_url(getattr(u, 'avatar', None))}
    if full:
        out['email'] = u.email
    return out


def token_json(row, current=False):
    return {'id': row.id, 'name': row.name, 'prefix': row.prefix, 'created': iso(row.created),
            'last_used': iso(row.last_used), 'expires_at': iso(row.expires_at), 'active': row.active,
            'current': current}


# ---------------------------------------------------------------- student side

def attempt_summary(cq):
    return {'id': cq.id, 'quiz': {'id': cq.vquiz.id, 'title': cq.vquiz.title},
            'status': S.attempt_state(cq), 'score': cq.score if cq.completed else None,
            'questions': len(cq.cproblems), 'calculator_ok': bool(cq.vquiz.calculator_ok),
            'assigned': iso(cq.create_date), 'started': iso(cq.startdate), 'submitted': iso(cq.compdate),
            'opens_at': iso(cq.opens_at), 'closes_at': iso(cq.closes_at), 'time_limit_minutes': cq.time_limit,
            'deadline': iso(cq.deadline())}


def my_quizzes_json(user):
    out = []
    for grp in attempts_by_quiz(user.cquizzes):
        out.append({'quiz': {'id': grp['vquiz'].id, 'title': grp['vquiz'].title},
                    'score_counted': grp['combined'], 'scoring_rule': grp['rule_key'],
                    'best_attempt': grp['best'].id if grp['best'] else None,
                    'counted_attempts': [c.id for c in grp['counted']],
                    'attempts': [attempt_summary(cq) for cq in grp['attempts']]})
    return out


def answer_json(cp):
    """A saved answer the way an app sends it back: text, a choice id, or a list of choice ids."""
    qt = get_qtype(cp.vproblem.qtype)
    if cp.submitted is None:
        return None
    if qt.uses_choices or qt.key == 'truefalse':
        picked = [str(i) for i in qt.picked(cp.submitted)]
        return picked if qt.multi else (picked[0] if picked else None)
    return cp.submitted


def question_json(cp):
    """One question as a student sees it while taking the quiz (no answers)."""
    qt = get_qtype(cp.vproblem.qtype)
    out = {'number': cp.ordinal, 'type': qt.key, 'text': cp.conc_prob,
           'image_url': static_url(problem_image(cp)), 'saved_answer': answer_json(cp)}
    if 'choices' in cp.conc_opts:
        out['choices'] = [{'id': str(i), 'text': t} for i, t in enumerate(cp.conc_opts['choices'])]
        out['multiple'] = bool(getattr(qt, 'multi', False))
    if cp.conc_opts.get('complex'):
        out['complex_numbers'] = True
    return out


def attempt_json(cq):
    out = attempt_summary(cq)
    out['questions'] = [question_json(cp) for cp in cq.cproblems]
    return out


def results_json(cq, show_answers):
    items = []
    for cp in cq.cproblems:
        it = transcript_item(cp)
        row = {'number': it.num, 'type': cp.vproblem.qtype, 'text': it.text, 'image_url': static_url(it.image),
               'your_answer': it.submitted, 'credit': it.credit, 'result': it.mark}
        if it.essay:
            row['feedback'] = it.feedback
            row['highlights'] = [{'start': s[0], 'end': s[1], 'kind': s[2]} for s in cp.highlights]
        if show_answers:
            row['correct_answer'] = it.correct
        items.append(row)
    return {'attempt': attempt_summary(cq), 'answers_shown': bool(show_answers), 'items': items}


# ---------------------------------------------------------------- teacher side

def labels_json(groups):
    return [{'id': g.id, 'name': g.title} for g in sorted(groups, key=lambda g: (g.title or '').lower())]


def archived_json(a):
    """An attempt in the archive (its results page is only in the single-item answer)."""
    return {'id': a.id, 'attempt_id': a.original_id, 'quiz_id': a.vquiz_id, 'quiz_title': a.quiz_title,
            'student_id': a.student_id, 'student_name': a.student_name,
            'student_account_deleted': S.archived_student(a) is None,
            'score': a.score, 'completed': a.completed, 'needs_review': a.needs_review,
            'started': iso(a.startdate), 'submitted': iso(a.compdate), 'assigned': iso(a.assigned),
            'archived': iso(a.archived_at), 'archived_by': a.archiver.username if a.archiver else None,
            'reason': a.reason, 'restore_blocked': S.restore_blocker(a),
            'folder': a.folder.name if a.folder and not a.folder.removed else 'Unsorted'}


def problem_json(vp, full=False):
    out = {'id': vp.id, 'title': vp.title, 'type': vp.qtype, 'question': vp.raw_prob,
           'calculator_ok': bool(vp.calculator_ok), 'created': iso(vp.create_date),
           'used_in_quizzes': [q.id for q in vp.vquizzes], 'labels': labels_json(vp.vpgroups)}
    if full:
        out['answer'] = vp.raw_ansr
        out['options'] = vp.options
    return out


def vquiz_json(vq, full=False):
    lay = layout.parse(vq.vpid_lst)
    out = {'id': vq.id, 'title': vq.title, 'questions_per_student': layout.question_count(lay),
           'calculator_ok': bool(vq.calculator_ok), 'shuffle_order': bool(vq.shuffle_order),
           'retake_rule': vq.retake_rule, 'hide_answers': bool(vq.hide_answers),
           'answers_released': bool(vq.answers_released), 'image_url': static_url(vq.image),
           'times_assigned': len(vq.cquizzes), 'labels': labels_json(vq.vqgroups)}
    if full:
        out['problems'] = lay
        out['image'] = vq.image
    return out


def teacher_attempt_json(cq):
    """Everything about one attempt, for a teacher: the student's answers, the correct ones, grading."""
    out = attempt_summary(cq)
    out['student'] = user_json(cq.taker)
    out['scoring_rule_override'] = cq.retake_rule
    items = []
    for cp in cq.cproblems:
        it = transcript_item(cp)
        row = {'id': cp.id, 'number': cp.ordinal, 'type': cp.vproblem.qtype, 'problem_id': cp.vproblem_id,
               'text': cp.conc_prob, 'image_url': static_url(it.image), 'your_answer': it.submitted,
               'raw_answer': cp.submitted, 'correct_answer': it.correct, 'credit': cp.credit,
               'feedback': cp.feedback, 'highlights': [{'start': s[0], 'end': s[1], 'kind': s[2]} for s in cp.highlights],
               'graded_by_teacher': not get_qtype(cp.vproblem.qtype).auto_graded}
        if 'choices' in cp.conc_opts:
            row['choices'] = cp.conc_opts['choices']
        if row['graded_by_teacher']:
            row['grading_notes'] = cp.vproblem.options.get('grading_notes')
        items.append(row)
    out['items'] = items
    return out


def student_results_json(user):
    out = []
    for grp in attempts_by_quiz(user.cquizzes):
        out.append({'quiz': {'id': grp['vquiz'].id, 'title': grp['vquiz'].title},
                    'score_counted': grp['combined'], 'scoring_rule': grp['rule_key'],
                    'rule_overridden': grp['overridden'],
                    'best_attempt': grp['best'].id if grp['best'] else None,
                    'counted_attempts': [c.id for c in grp['counted']],
                    'attempts': [attempt_summary(cq) for cq in grp['attempts']]})
    return out


def message_json(m):
    return {'id': m.id, 'student_id': m.student_id, 'from_teacher': m.from_teacher, 'kind': m.kind,
            'sender': m.sender.username if m.sender else None, 'body': m.body, 'link': m.link,
            'created': iso(m.created), 'pinned': bool(m.pinned),
            'seen_by_student': m.seen_by_student, 'seen_by_teacher': m.seen_by_teacher}

