"""Building the quiz-taking form, grading it, and making the transcript.

Python only gathers plain data (QuizItem, TranscriptItem); all layout lives
in the templates quiz_take.html and transcript_body.html.
"""
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any, Optional

from flask import render_template
from flask_wtf import FlaskForm
from markupsafe import Markup
from wtforms import SubmitField

from .qtypes import get_qtype, plain_numbers_only

fieldname_base = 'Number{}'

#stored transcripts made by this code start with this marker; older ones
#are Jinja template text and are cleaned up by legacy_transcript()
TRANSCRIPT_V2 = '<!--transcript v2-->'


def qtype_of(cprob):
    return get_qtype(cprob.vproblem.qtype)


def teacher_grades(cprob):
    """The teacher gives this answer its credit: written answers and paper pages always,
    and a Short text answer that came close (to_check)."""
    return not qtype_of(cprob).auto_graded or bool(cprob.conc_opts.get('to_check'))


def problem_image(cprob):
    """This student's picture for a problem (picked at random when there are several)."""
    return cprob.conc_opts.get('image') or cprob.vproblem.image


#create the quiz-taking form for one assigned quiz
def quiz_form_class(cquiz):
    #class defined per call so fields never leak between quizzes
    class QuizTakeForm(FlaskForm):
        submit = SubmitField('Hand it in')
    for cprob in cquiz.cproblems:
        field = qtype_of(cprob).make_field(fieldname_base.format(cprob.ordinal), cprob.conc_opts)
        setattr(QuizTakeForm, fieldname_base.format(cprob.ordinal), field)
    return QuizTakeForm


@dataclass
class QuizItem:
    """One question as shown on the quiz-taking page."""
    num: int
    text: str
    image: Optional[str]
    field: Any
    qtype: str
    complex: bool = False
    plain: bool = False  # a number answer that must be just the number(s): no formula (the owner, 2026-10-24)


def quiz_items(cquiz, form):
    return [QuizItem(num=cp.ordinal, text=cp.conc_prob, image=problem_image(cp),
                     field=form[fieldname_base.format(cp.ordinal)], qtype=qtype_of(cp).key,
                     complex=bool(cp.conc_opts.get('complex')),
                     plain=qtype_of(cp).key == 'numeric' and plain_numbers_only(cp.vproblem.options or {}))
            for cp in cquiz.cproblems]


#save answers and auto-grade; returns True when an instructor still needs to grade.
#answers: {question number: answer as the form or API sends it}. Questions not
#in it keep their autosaved answer, so answers=None (time ran out) grades what was saved.
def record_answers(cquiz, answers=None):
    needs_review = False
    for cprob in cquiz.cproblems:
        qt = qtype_of(cprob)
        if answers is not None and cprob.ordinal in answers:
            cprob.submitted = qt.to_stored(answers[cprob.ordinal])
        elif cprob.submitted is None:
            cprob.submitted = qt.to_stored(None)
        if qt.auto_graded:
            cprob.credit = qt.grade(cprob.submitted, cprob.conc_ansr or '', cprob.conc_opts, cprob.vproblem.options)
            #None: not on the list, but maybe right (Short text: any wrong answer written, e.g. a
            #misspelling or "a brown horse" for "horse"), so the teacher checks it in Grading
            opts = {k: v for k, v in cprob.conc_opts.items() if k not in ('to_check', 'ai_right')}
            if cprob.credit is None:
                opts['to_check'] = True
                needs_review = True
            cprob.conc_opts = opts
        else:
            #a blank essay needs no reading: it's simply 0
            cprob.credit = 0.0 if qt.is_blank(cprob.submitted) else None
            needs_review = needs_review or cprob.credit is None
    #the Short text answers still to check: a small AI model looks first, and marks right only the ones
    #it's sure have the key items (the owner, 2026-10-25, CP4); the rest stay with the teacher
    if needs_review and ai_check_answers(cquiz):
        needs_review = any(cp.credit is None for cp in cquiz.cproblems)
    cquiz.compdate = datetime.now()
    return needs_review


def ai_check_answers(cquiz):
    """Ask the AI about this attempt's Short text answers waiting to be checked (one call for them all).
    Returns True when any was marked right. Any trouble leaves them for the teacher."""
    from flask import current_app
    from app import db, tuning
    from .models import AICall
    from . import ai_helper
    key = current_app.config.get('ANTHROPIC_API_KEY')
    waiting = [cp for cp in cquiz.cproblems if cp.credit is None and cp.conc_opts.get('to_check')]
    if not waiting or not key or tuning.get('ai_short_answers') != 'on':
        return False
    items = [{'n': cp.ordinal, 'question': cp.conc_prob or '', 'answer': cp.submitted or '',
              'accepted': [a.strip() for a in (cp.conc_ansr or '').splitlines() if a.strip()]} for cp in waiting]
    log = AICall(user_id=cquiz.assignee, kind='grade', request='{} short answer(s) in attempt {}'.format(len(items), cquiz.id))
    try:
        right, usage = ai_helper.check_short_answers(key, items)
        log.ok, log.input_tokens, log.output_tokens = True, usage.get('input_tokens'), usage.get('output_tokens')
    except Exception as exc:  # never let the check stop a hand-in
        current_app.logger.warning('AI short-answer check failed: {}'.format(exc))
        right = {}
    db.session.add(log)
    for cp in waiting:
        if right.get(cp.ordinal):
            cp.credit = 1.0
            cp.conc_opts = dict({k: v for k, v in cp.conc_opts.items() if k != 'to_check'}, ai_right=True)
    return bool(right)


def form_answers(cquiz, form):
    """{question number: answer} from the quiz page's form."""
    return {cp.ordinal: form[fieldname_base.format(cp.ordinal)].data for cp in cquiz.cproblems}


def quiz_score(cquiz):
    probs = cquiz.cproblems
    if not probs:
        return 0.0
    #(pages to look at aren't scored; a quiz of only those is done: 100%, the owner 2026-10-19)
    scored = [cp for cp in probs if not get_qtype(cp.vproblem.qtype).look]
    if not scored:
        return 100.0
    return 100.0 * sum(cp.credit or 0 for cp in scored) / len(scored)


#finish a quiz: score it and save the permanent transcript
def finalize(cquiz):
    cquiz.score = quiz_score(cquiz)
    cquiz.needs_review = False
    cquiz.completed = True
    cquiz.transcript = TRANSCRIPT_V2 + build_transcript(cquiz)


def highlighted(text, spans):
    """Student text with [start, end, 'right'|'wrong'] spans wrapped in <mark>.
    The text is escaped piece by piece, so nothing the student typed becomes HTML."""
    text = text or ''
    out, pos = [], 0
    clean = []
    for span in sorted(spans or [], key=lambda s: s[0]):
        try:
            start, end, kind = int(span[0]), int(span[1]), span[2]
        except (TypeError, ValueError, IndexError):
            continue
        start, end = max(start, pos), min(end, len(text))
        if kind not in ('right', 'wrong') or end <= start:
            continue
        clean.append((start, end, kind))
        pos = end
    pos = 0
    for start, end, kind in clean:
        out.append(escape(text[pos:start]))
        out.append('<mark class="hl-{}">{}</mark>'.format(kind, escape(text[start:end])))
        pos = end
    out.append(escape(text[pos:]))
    return Markup(''.join(out))


@dataclass
class TranscriptItem:
    """One question as shown on the transcript and the grading page."""
    num: int
    text: str
    image: Optional[str]
    essay: bool
    submitted: str
    submitted_html: Optional[Markup]
    correct: str
    credit: Optional[float]
    feedback: Optional[str]
    #pick-one / pick-several / true-false: every choice the student saw, in their order,
    #as {'text', 'picked', 'right'}; None for other types
    choices: Optional[list] = None
    paper: bool = False  # done on paper: no typed answer to show
    look: bool = False   # a page to look at: nothing answered, not graded
    check: bool = False  # an automatic type's answer the teacher checks (Short text not on the list)
    ai_right: bool = False  # Short text marked right by the AI check (shown to teachers only)

    @property
    def mark(self):
        """'ok', 'bad' or 'partial', for the ✓ / ✗ / ◐ symbol."""
        if self.credit == 1:
            return 'ok'
        return 'bad' if not self.credit else 'partial'


def transcript_choices(qt, cp):
    """The choices this student saw, which they picked, and which are correct
    (left unmarked when several combinations of checked boxes count, as in combos)."""
    opts = cp.conc_opts or {}
    if not hasattr(qt, 'picked') or not opts.get('choices'):
        return None
    picked = set(qt.picked(cp.submitted))
    right = set() if opts.get('combos') else set(opts.get('correct') or [])
    return [{'text': text, 'picked': i in picked, 'right': i in right} for i, text in enumerate(opts['choices'])]


def transcript_item(cp):
    qt = qtype_of(cp)
    return TranscriptItem(
        num=cp.ordinal, text=cp.conc_prob, image=problem_image(cp),
        essay=not qt.auto_graded,
        submitted=qt.show_submitted(cp.submitted, cp.conc_opts),
        submitted_html=None if qt.auto_graded else highlighted(cp.submitted, cp.highlights),
        correct=qt.show_correct(cp.conc_ansr, cp.conc_opts),
        credit=cp.credit,
        feedback=cp.feedback,
        choices=transcript_choices(qt, cp),
        paper=qt.paper, look=qt.look,
        check=qt.auto_graded and bool((cp.conc_opts or {}).get('to_check')),
        ai_right=bool((cp.conc_opts or {}).get('ai_right')),
    )


def transcript_items(cquiz):
    return [transcript_item(cp) for cp in cquiz.cproblems]


def build_transcript(cquiz):
    return render_template('transcript_body.html', cq=cquiz, items=transcript_items(cquiz))


def legacy_transcript(stored, title):
    """Older transcripts were saved as Jinja template text; show just their HTML."""
    body = stored
    for tag in ('{% extends "base.html" %}', '{% block content %}', '{% endblock %}'):
        body = body.replace(tag, '')
    return body.replace('{{ title }}', escape(title or ''))


def transcript_html(cquiz, title):
    stored = cquiz.transcript or ''
    if stored.startswith(TRANSCRIPT_V2):
        #shown from the same saved data the stored record was made from, so pages
        #made before a change in how results look (or what's shown) get it too
        return Markup(build_transcript(cquiz))
    return Markup('<div class="card legacy-transcript">{}</div>'.format(legacy_transcript(stored, title)))
