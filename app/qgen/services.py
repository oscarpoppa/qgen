"""What teachers and students can do with quizzes, independent of how they ask.

The web pages (routes.py) and the REST API (app/api) both call these
functions, so grading, randomizing and the rules around them can never
drift apart. Nothing here reads the request, flashes messages or renders
pages; problems are reported by raising ServiceError (worded for people)
or by returning lists of plain-language errors.
"""
import json
import random
from datetime import datetime

from flask import url_for, render_template
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError

from app import db, tuning
from app.messages.models import notify, notify_teachers
from . import layout
from .formfact import record_answers, finalize, TRANSCRIPT_V2
from .friendly import FriendlyError
from .models import CQuiz, VQuiz, VProblem, CProblem, VPGroup, VQGroup, ArchivedAttempt, ArchiveFolder, RETAKE_RULES
from .qtypes import get_qtype

#answers are still accepted a little after the deadline (slow connections, the
#auto-submit): "Grace after a quiz's time is up" in Technical settings (app/tuning.py)


class ServiceError(ValueError):
    """Something that was asked for can't be done, worded for people to read."""


# ---------------------------------------------------------------- subjects

#a teacher's own subjects for sorting problems and quizzes (separate lists; an item can
#be in several, or none). Stored in the old VPGroup / VQGroup tables. Not the "2 of
#these 6" question groups inside a quiz (layout.py).
SUBJECT_KINDS = {'problems': (VPGroup, VProblem, 'vpgroups', 'vproblems'),
                 'quizzes': (VQGroup, VQuiz, 'vqgroups', 'vquizzes')}
SUBJECT_NAME_MAX = 64


def subject_kind(kind):
    if kind not in SUBJECT_KINDS:
        raise ServiceError('Unknown kind of folder "{}".'.format(kind))
    return SUBJECT_KINDS[kind]


def subjects(kind):
    """The subjects of one kind, by name."""
    group_cls = subject_kind(kind)[0]
    return sorted(group_cls.query.all(), key=lambda g: (g.title or '').lower())


def _subject_name(kind, name, subject=None):
    name = ' '.join((name or '').split())
    if not name:
        raise ServiceError('Please give the folder a name.')
    if len(name) > SUBJECT_NAME_MAX:
        raise ServiceError('Folder names can be at most {} characters.'.format(SUBJECT_NAME_MAX))
    for other in subjects(kind):
        if other is not subject and (other.title or '').lower() == name.lower():
            raise ServiceError('There\'s already a folder called "{}".'.format(other.title))
    return name


def create_subject(kind, name):
    group_cls = subject_kind(kind)[0]
    subject = group_cls(title=_subject_name(kind, name))
    db.session.add(subject)
    _commit_subject()
    return subject


def rename_subject(kind, subject, name):
    subject.title = _subject_name(kind, name, subject)
    _commit_subject()


def _commit_subject():
    try:
        db.session.commit()
    except IntegrityError:
        #another teacher made one with the same name a moment ago
        db.session.rollback()
        raise ServiceError('There\'s already a folder with that name.')


def delete_subject(subject):
    """Delete a subject; the problems or quizzes in it are kept."""
    db.session.delete(subject)
    db.session.commit()


def get_subject(kind, subject_id):
    try:
        return db.session.get(subject_kind(kind)[0], int(subject_id))
    except (TypeError, ValueError):
        return None


def _ids(values):
    out = set()
    for v in values or []:
        try:
            out.add(int(v))
        except (TypeError, ValueError):
            continue
    return out


def set_subjects(kind, item, ids):
    """Put an item in exactly these subjects (from its edit form; committed by the caller).
    Unknown ids are ignored."""
    group_cls, _item_cls, rel, _back = subject_kind(kind)
    wanted = _ids(ids)
    setattr(item, rel, group_cls.query.filter(group_cls.id.in_(wanted)).all() if wanted else [])


def file_items(kind, item_ids, subject, add=True):
    """Add several problems (or quizzes) to a subject, or take them out of it. Items
    already (or not) in it are skipped. Returns how many changed."""
    _group_cls, item_cls, rel, _back = subject_kind(kind)
    ids = _ids(item_ids)
    changed = 0
    for item in item_cls.query.filter(item_cls.id.in_(ids)).all() if ids else []:
        current = getattr(item, rel)
        if add and subject not in current:
            current.append(subject)
            changed += 1
        elif not add and subject in current:
            current.remove(subject)
            changed += 1
    try:
        db.session.commit()
    except IntegrityError:
        #another teacher filed the same item at the same moment: it's in there either way
        db.session.rollback()
    return changed


def subject_choices(kind):
    """The subject menu: [(value, label, count)] for All, No subject and each subject."""
    _group_cls, item_cls, rel, back = subject_kind(kind)
    out = [('all', 'All', item_cls.query.count()),
           ('none', 'No folder', item_cls.query.filter(~getattr(item_cls, rel).any()).count())]
    for g in subjects(kind):
        out.append((str(g.id), g.title, len(getattr(g, back))))
    return out


def subject_boxes(kind):
    """The containers on the Problems (Quizzes) page: [(subject, items)] by subject name,
    then (None, the items in no subject) for Unsorted. An item in several subjects is in
    each of their containers. Newest items first."""
    group_cls, item_cls, rel, back = subject_kind(kind)
    newest = lambda items: sorted(items, key=lambda i: i.id, reverse=True)
    boxes = [(g, newest(getattr(g, back))) for g in subjects(kind)]
    boxes.append((None, item_cls.query.filter(~getattr(item_cls, rel).any()).order_by(item_cls.id.desc()).all()))
    return boxes


def new_subject_name_error(kind, name):
    """For the "or make a new subject" box on the edit forms: a problem with the name,
    or None. A name that is already a subject (in any case) is fine: that one is used."""
    name = ' '.join((name or '').split())
    if name and len(name) > SUBJECT_NAME_MAX:
        return 'Folder names can be at most {} characters.'.format(SUBJECT_NAME_MAX)
    return None


def subject_named(kind, name):
    """The subject with this name (any case), made if there isn't one yet; committed."""
    name = ' '.join((name or '').split())
    for g in subjects(kind):
        if (g.title or '').lower() == name.lower():
            return g
    try:
        return create_subject(kind, name)
    except ServiceError:
        #made by someone else a moment ago
        return next(g for g in subjects(kind) if (g.title or '').lower() == name.lower())


def valid_subject_choice(kind, choice):
    """'all', 'none' or an existing subject's id (as text); anything else is 'all'."""
    if choice in ('all', 'none'):
        return choice
    subject = get_subject(kind, choice)
    return str(subject.id) if subject else 'all'


# ---------------------------------------------------------------- problems

def problem_errors(qtype, question, answer, options):
    """Plain-language errors; empty when the problem is ready to save."""
    return get_qtype(qtype).validate(question, answer, options)


def save_problem(vp, qtype, title, question, answer, options, calculator_ok=False):
    """Check and save a problem (new or existing). Returns errors; saves only if there are none."""
    errors = problem_errors(qtype, question, answer, options)
    if not (title or '').strip():
        errors = ['Please give the problem a short title.'] + errors
    if vp.id is not None and vp.qtype and qtype != vp.qtype and vp.cproblems:
        #students' answers were given (and are shown and graded) as the old type
        errors = ['Students have already been given this problem as "{}", so its question type can\'t change. '
                  'Make a new problem instead (the old one keeps their answers).'.format(get_qtype(vp.qtype).label)] + errors
    if errors:
        return errors
    new = vp.id is None
    if new:
        db.session.add(vp)
    vp.qtype, vp.title, vp.raw_prob, vp.raw_ansr = qtype, title.strip(), question, answer
    vp.options = options
    #first picture kept in the old column for older pages and quizzes
    images = options.get('images') or []
    vp.image = images[0]['file'] if images else None
    vp.calculator_ok = bool(calculator_ok)
    vp.save()
    return []


def problem_delete_blocker(vp):
    """Why a problem can't be deleted, or None if it can."""
    if vp.vquizzes:
        return 'Problem "{}" is used by these quizzes: {}.'.format(
            vp.title, ', '.join('"{}"'.format(q.title) for q in vp.vquizzes))
    if vp.cproblems:
        #students' answers to it are part of their records
        return ('Problem "{}" has {} student answer{} on record. You can take it out of quizzes instead; '
                'it just won\'t be used again.'.format(vp.title, len(vp.cproblems), '' if len(vp.cproblems) == 1 else 's'))
    return None


def delete_problem(vp):
    blocker = problem_delete_blocker(vp)
    if blocker:
        raise ServiceError(blocker)
    db.session.delete(vp)
    db.session.commit()


def _old_markup(vp):
    """Written in the old {{...}} markup (no longer supported)."""
    options = vp.options or {}
    if options.get('markup'):
        return options['markup'] == 'legacy'
    return '{{' in (vp.raw_prob or '')


def old_markup_cleanup(apply=False):
    """Everything still tied to the old {{...}} markup: its problems, every quiz that uses
    one (whole quizzes, even if they also have new problems), and every student attempt
    at those quizzes or with one of those problems in it. With apply, deletes it all for
    good (attempts are not archived) and commits. Returns what was (or would be) removed:
    {'problems': [(id, title)], 'quizzes': [(id, title)], 'attempts': [(id, quiz id, student)]}."""
    problems = [vp for vp in VProblem.query.order_by(VProblem.id).all() if _old_markup(vp)]
    pids = {vp.id for vp in problems}
    quizzes = [vq for vq in VQuiz.query.order_by(VQuiz.id).all()
               if pids & ({p.id for p in vq.vproblems} | set(layout.all_ids(_safe_layout(vq.vpid_lst))))]
    qids = {vq.id for vq in quizzes}
    attempts = CQuiz.query.filter(db.or_(
        CQuiz.vquiz_id.in_(qids or [0]),
        CQuiz.id.in_(db.session.query(CProblem.cquiz_id).filter(CProblem.vproblem_id.in_(pids or [0]))),
    )).order_by(CQuiz.id).all()
    found = {'problems': [(vp.id, vp.title) for vp in problems],
             'quizzes': [(vq.id, vq.title) for vq in quizzes],
             'attempts': [(cq.id, cq.vquiz_id, cq.taker.username if cq.taker else str(cq.assignee)) for cq in attempts]}
    if apply:
        for cq in attempts:
            _erase_attempt(cq)
        db.session.flush()
        for vq in quizzes:
            _forget_notices(['/quiz/listvq/{}'.format(vq.id)])
            db.session.delete(vq)
        db.session.flush()
        for vp in problems:
            db.session.delete(vp)
        db.session.commit()
    return found


def _safe_layout(text):
    try:
        return layout.parse(text or '[]')
    except (layout.LayoutError, TypeError, ValueError):
        return []


def instantiate_problem(vprob, rng=random):
    """One student's own random version of a problem: (text, answer, extra data)."""
    qt = get_qtype(vprob.qtype)
    #problems are checked before saving, but if a rare draw still can't be
    #worked out (e.g. an edge case in an old problem), draw again
    for attempt in range(50):
        try:
            return qt.instantiate(vprob.raw_prob, vprob.raw_ansr, vprob.options, rng)
        except FriendlyError:
            if attempt == 49:
                raise ServiceError('Problem "{}" couldn\'t be set up; please open it and check it.'.format(vprob.title))


def preview_problem(qtype, question, answer, options, count=3):
    """A few sample versions, without saving; (errors, samples)."""
    errors = problem_errors(qtype, question, answer, options)
    if errors:
        return errors, []
    qt, rng, samples = get_qtype(qtype), random.Random(), []
    for _ in range(count):
        prob, ansr, co = qt.instantiate(question, answer, options, rng)
        samples.append({'text': prob, 'correct': qt.show_correct(ansr, co), 'choices': co.get('choices'),
                        'right': co.get('correct', []), 'image': co.get('image')})
    return [], samples


# ---------------------------------------------------------------- quizzes

QUIZ_SETTINGS = ('image', 'calculator_ok', 'shuffle_order', 'retake_rule', 'hide_answers')


def check_layout(value):
    """A quiz's problem list (text, JSON or already parsed) -> (layout, errors)."""
    try:
        lay = layout.parse(value) if isinstance(value, str) else layout.parse(json.dumps(value or []))
    except (layout.LayoutError, TypeError, ValueError) as exc:
        return [], [str(exc) if isinstance(exc, layout.LayoutError) else 'The list of problems couldn\'t be read.']
    if not lay:
        return lay, ['Choose at least one problem.']
    missing = [n for n in set(layout.all_ids(lay)) if not db.session.get(VProblem, n)]
    if missing:
        return lay, ['These problems no longer exist: {}'.format(', '.join(map(str, sorted(missing))))]
    return lay, layout.check(lay)


def save_vquiz(vq, title, problems, author_id=None, **settings):
    """Check and save a quiz (new or existing). Returns errors; saves only if there are none."""
    lay, errors = check_layout(problems)
    if not (title or '').strip():
        errors = ['Please give the quiz a title.'] + errors
    if settings.get('retake_rule') and settings['retake_rule'] not in RETAKE_RULES:
        errors.append('Unknown retake rule "{}".'.format(settings['retake_rule']))
    if errors:
        return errors
    new = vq.id is None
    if new:
        vq.author_id = author_id
        #in the session before links are made, so lookups below don't trip over it
        db.session.add(vq)
    vq.title = title.strip()
    if not new and settings.get('retake_rule') and settings['retake_rule'] != vq.retake_rule:
        #a new scoring rule for the quiz applies to everyone, including students who
        #had been given their own on "Results by student"
        for cq in vq.cquizzes:
            cq.retake_rule = None
    for key in QUIZ_SETTINGS:
        if key in settings:
            if key == 'hide_answers' and vq.hide_answers != settings[key]:
                vq.answers_released = False
            setattr(vq, key, settings[key])
    vq.vpid_lst = layout.dumps(lay)
    vq.vproblems = [db.session.get(VProblem, a) for a in set(layout.all_ids(lay))]
    vq.save()
    return []


def vquiz_delete_blocker(vq):
    if vq.cquizzes:
        return 'Quiz "{}" has been assigned {} time{}. Delete those assignments first.'.format(
            vq.title, len(vq.cquizzes), '' if len(vq.cquizzes) == 1 else 's')
    return None


def delete_vquiz(vq):
    """Delete a quiz that hasn't been assigned (students' attempts are deleted one by one)."""
    blocker = vquiz_delete_blocker(vq)
    if blocker:
        raise ServiceError(blocker)
    _forget_notices(['/quiz/listvq/{}'.format(vq.id)])
    db.session.delete(vq)
    db.session.commit()


def _attempt_links(cq):
    """The pages notices may point to for one attempt."""
    return ['/quiz/take/{}'.format(cq.id), '/quiz/review/{}'.format(cq.id)]


def _forget_notices(links):
    """Notices whose Open would lead to something that no longer exists."""
    from app.messages.models import Message, MessageRead
    if links:
        ids = Message.query.filter(Message.kind == 'notice', Message.link.in_(links)).with_entities(Message.id)
        MessageRead.query.filter(MessageRead.message_id.in_(ids)).delete(synchronize_session=False)
        Message.query.filter(Message.kind == 'notice', Message.link.in_(links)).delete(synchronize_session=False)


def release_answers(vq, released):
    """Show (or hide again) correct answers on results pages; tells students when shown."""
    vq.answers_released = bool(released)
    if vq.answers_released:
        for cq in {c.assignee: c for c in vq.cquizzes if c.completed}.values():
            notify(cq.assignee, 'The correct answers for "{}" are now on your results page.'.format(vq.title),
                   url_for('qgen.qtake', cidx=cq.id))
    vq.save()


def release_answers_to(vq, student_id, released):
    """Show (or hide again) the correct answers to one student, on all of that student's
    attempts at this quiz, while the quiz still hides them from everyone else. Tells the
    student when shown. Returns the attempts changed."""
    attempts = CQuiz.query.filter_by(vquiz_id=vq.id, assignee=student_id).all()
    if not attempts:
        raise ServiceError('That student doesn\'t have "{}".'.format(vq.title))
    for cq in attempts:
        cq.answers_released = bool(released)
    finished = [cq for cq in attempts if cq.completed]
    if released and finished:
        latest = max(finished, key=lambda c: c.id)
        notify(student_id, 'The correct answers for "{}" are now on your results page.'.format(vq.title),
               url_for('qgen.qtake', cidx=latest.id))
    db.session.commit()
    return attempts


# ---------------------------------------------------------------- viewing (nothing saved)

def _sample_item(vp, rng, num=None):
    """One student's version of a problem, for viewing only."""
    qt = get_qtype(vp.qtype)
    prob, ansr, opts = instantiate_problem(vp, rng)
    return {'num': num, 'vpid': vp.id, 'title': vp.title, 'qtype': qt.label, 'essay': not qt.auto_graded,
            'text': prob, 'correct': qt.show_correct(ansr, opts), 'choices': opts.get('choices'),
            'right': opts.get('correct', []), 'image': opts.get('image')}


def sample_problem(vp, count=3):
    """A few versions of a saved problem, as different students would get them."""
    rng = random.Random()
    return [_sample_item(vp, rng, n) for n in range(1, count + 1)]


def sample_quiz(vq):
    """One student's version of a whole quiz, drawn the way create_cquiz draws it
    (groups picked, order shuffled if the quiz says so), without saving anything."""
    rng = random.Random()
    ordered = layout.draw(layout.parse(vq.vpid_lst), rng)
    if vq.shuffle_order:
        rng.shuffle(ordered)
    items = []
    for pid in ordered:
        vp = db.session.get(VProblem, pid)
        if vp is not None:
            items.append(_sample_item(vp, rng, len(items) + 1))
    return items


# ---------------------------------------------------------------- assigning

def create_cquiz(vquiz, assignee, opens_at=None, closes_at=None, time_limit=None):
    """One student's own copy of a quiz. Raises ServiceError if it can't be made."""
    try:
        cq = CQuiz(vquiz_id=vquiz.id, assignee=assignee.id, opens_at=opens_at, closes_at=closes_at, time_limit=time_limit)
        #only a quiz that opens later gets an "it's open now" notice (see announce_opened)
        cq.open_notice_sent = not (opens_at and opens_at > datetime.now())
        #groups ("2 of these 6") are drawn separately for each student
        ordered = layout.draw(layout.parse(vquiz.vpid_lst), random)
        #so "question 1 is B" means nothing to the student next door
        if vquiz.shuffle_order:
            random.shuffle(ordered)
        for ordinal, pid in enumerate(ordered, 1):
            vprob = db.session.get(VProblem, pid)
            prob, ansr, opts = instantiate_problem(vprob)
            cp = CProblem(ordinal=ordinal, conc_prob=prob, conc_ansr=ansr, vproblem_id=vprob.id)
            cp.conc_opts = opts
            cq.cproblems.append(cp)
        cq.save()
        return cq
    except ServiceError:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        raise ServiceError('Couldn\'t create "{}" for {}: {}'.format(vquiz.title, assignee.username, exc))


def time_limit_error(opens_at, closes_at, time_limit, now=None):
    """A time limit can't be longer than the time a student has: from opening (or, with
    no opening time, from now) until closing. A message saying so, or None if it fits
    (or there's no limit or no closing time)."""
    if not (closes_at and time_limit):
        return None
    start = opens_at or (now or datetime.now())
    if closes_at <= start:
        return None  # closing before opening is its own error; already closed isn't this one
    window = int((closes_at - start).total_seconds() // 60)
    if time_limit <= window:
        return None
    if opens_at:
        return ('The time limit ({} minutes) is longer than the time between opening and closing ({} minute{}). '
                'Make it {} minutes or less, or give more time between opening and closing.'
                .format(time_limit, window, '' if window == 1 else 's', window))
    return ('The time limit ({} minutes) is longer than the time left until the quiz closes ({} minute{}). '
            'Make it {} minutes or less, or close it later.'
            .format(time_limit, window, '' if window == 1 else 's', window))


def assign(vquiz, students, opens_at=None, closes_at=None, time_limit=None, by=None):
    """Give each student a separate copy; returns (created quizzes, [(student, error), ...]).
    `by` is the teacher assigning it: the teachers' notices say who assigned what."""
    if opens_at and closes_at and closes_at <= opens_at:
        raise ServiceError('The closing time must be after the opening time.')
    if time_limit is not None and not 1 <= time_limit <= 600:
        raise ServiceError('The time limit must be between 1 and 600 minutes.')
    too_long = time_limit_error(opens_at, closes_at, time_limit)
    if too_long:
        raise ServiceError(too_long)
    created, failed = [], []
    for student in students:
        try:
            cq = create_cquiz(vquiz, student, opens_at, closes_at, time_limit)
        except ServiceError as exc:
            failed.append((student, str(exc)))
            continue
        when = ' It opens {}.'.format(cq.opens_at.strftime('%b %d at %I:%M %p')) if cq.opens_at else ''
        notify(student.id, 'New quiz: "{}".{}'.format(vquiz.title, when), url_for('qgen.qtake', cidx=cq.id))
        created.append(cq)
    if created:
        _notice_assigned(vquiz, created, by, opens_at, closes_at, time_limit)
    db.session.commit()
    return created, failed


def _notice_assigned(vquiz, created, by, opens_at, closes_at, time_limit):
    """One notice for the teachers per assignment (not one per student), e.g.
    'dan assigned "Quiz 3" to 3 students: sam, kim, lee. Due Oct 03 at 05:00 PM.'"""
    names = [cq.taker.username for cq in created if cq.taker]
    shown = ', '.join(names[:6]) + (' and {} more'.format(len(names) - 6) if len(names) > 6 else '')
    details = []
    if opens_at:
        details.append('Opens {}.'.format(opens_at.strftime('%b %d at %I:%M %p')))
    if closes_at:
        details.append('Due {}.'.format(closes_at.strftime('%b %d at %I:%M %p')))
    if time_limit:
        details.append('{} minute time limit.'.format(time_limit))
    body = '{} assigned "{}" to {} student{}: {}.{}'.format(
        by.username if by else 'A teacher', vquiz.title, len(names), '' if len(names) == 1 else 's', shown,
        (' ' + ' '.join(details)) if details else '')
    #a notice belongs to one person's record: the assigning teacher's (so the panel shows that
    #teacher's picture), or the first student's when assigned without a signed-in teacher
    #"Open" goes to the quiz that was assigned
    notify_teachers(by.id if by else created[0].assignee, body, _link('qgen.list_vquiz', vqid=vquiz.id))


def retake(cq, by=None):
    """A fresh copy, with new values, of a quiz the student has taken. `by` is the
    teacher giving it: the student and the teachers each get a notice."""
    if not (cq.completed or cq.needs_review):
        raise ServiceError('{} hasn\'t finished "{}" yet.'.format(cq.taker.username, cq.vquiz.title))
    new = create_cquiz(cq.vquiz, cq.taker)
    new.retake_rule = cq.retake_rule
    #answers released to this student stay released on the new attempt
    new.answers_released = cq.answers_released
    notify(cq.assignee, 'You can try "{}" again.'.format(cq.vquiz.title), url_for('qgen.qtake', cidx=new.id))
    #for the teachers; "Open" goes to that student's results
    notify_teachers(cq.assignee, '{} gave {} a retake of "{}".'.format(by.username if by else 'A teacher', cq.taker.username, cq.vquiz.title),
                    _link('qgen.list_user', uid=cq.assignee))
    db.session.commit()
    return new


def _erase_attempt(cq):
    """Remove one attempt from the live tables (and notices pointing to it); not committed."""
    _forget_notices(_attempt_links(cq))
    CProblem.query.filter_by(cquiz_id=cq.id).delete()
    db.session.delete(cq)


def delete_attempt(cq, by=None, reason='deleted'):
    """Take one attempt away from the student and keep it in the Archive, where a teacher
    can look at it, restore it or delete it for good. The student's last attempt at a
    quiz takes the quiz's box off their My quizzes."""
    archived = archive_attempt(cq, by, reason)
    db.session.commit()
    return archived


# ---------------------------------------------------------------- the archive

#what an archived attempt keeps: a compact, readable JSON record (no page markup). The
#results page is drawn from it when looked at. Format 2: each question also notes its
#question type and picture, so it still reads right after the problem is deleted.
ARCHIVE_FORMAT = 2


def _plain(value):
    if isinstance(value, datetime):
        return {'datetime': value.isoformat()}
    return value


def _row_data(obj):
    """Every stored field of a row, by attribute name, as JSON-safe values."""
    return {attr.key: _plain(getattr(obj, attr.key)) for attr in sa_inspect(obj).mapper.column_attrs}


def _fill_row(obj, data):
    """Set the fields this version of the app knows; anything else is skipped, and
    fields added later keep their defaults."""
    for attr in sa_inspect(type(obj)).column_attrs:
        if attr.key not in data:
            continue
        value = data[attr.key]
        if isinstance(value, dict) and set(value) == {'datetime'}:
            value = datetime.fromisoformat(value['datetime'])
        setattr(obj, attr.key, value)


def archive_record(cq):
    """The JSON kept for an archived attempt: the attempt and each question as stored,
    without the saved results page (it's drawn from this same data), except for
    results saved before the upgrade, whose old page is the only record."""
    attempt = _row_data(cq)
    if (attempt.get('transcript') or '').startswith(TRANSCRIPT_V2):
        attempt['transcript'] = TRANSCRIPT_V2
    problems = []
    for cp in cq.cproblems:
        row = _row_data(cp)
        row['qtype'] = cp.vproblem.qtype if cp.vproblem else 'numeric'
        row['problem_image'] = cp.vproblem.image if cp.vproblem else None
        problems.append(row)
    return {'v': ARCHIVE_FORMAT, 'attempt': attempt, 'problems': problems,
            'quiz_image': cq.vquiz.image if cq.vquiz else None}


def archive_attempt(cq, by=None, reason='deleted'):
    """Move an attempt into the archive (not committed: the caller commits, so the copy
    and the removal happen together or not at all)."""
    record = archive_record(cq)
    archived = ArchivedAttempt(
        original_id=cq.id, vquiz_id=cq.vquiz_id, student_id=cq.assignee,
        student_name=cq.taker.username if cq.taker else '(unknown)',
        quiz_title=cq.vquiz.title or 'Untitled',
        score=cq.score, completed=bool(cq.completed), needs_review=bool(cq.needs_review),
        startdate=cq.startdate, compdate=cq.compdate, assigned=cq.create_date,
        archived_at=datetime.now(), archived_by=by.id if by else None, reason=reason,
        folder_id=student_folder(cq.taker).id if cq.taker else None,
        problem_ids=',' + ''.join('{},'.format(p['vproblem_id']) for p in record['problems']),
        data=json.dumps(record, separators=(',', ':'), ensure_ascii=False))
    db.session.add(archived)
    db.session.flush()
    _erase_attempt(cq)
    return archived


def archived_results(a):
    """The results page of an archived attempt, drawn from its record, as a teacher
    sees it (every answer and the correct ones)."""
    from types import SimpleNamespace as NS
    from markupsafe import Markup
    from .formfact import legacy_transcript, transcript_item
    data = json.loads(a.data)
    attempt = data['attempt']
    stored = attempt.get('transcript') or ''
    if attempt.get('completed') and stored and not stored.startswith(TRANSCRIPT_V2):
        return Markup('<div class="card legacy-transcript">{}</div>'.format(legacy_transcript(stored, a.quiz_title)))
    when = lambda key: datetime.fromisoformat(attempt[key]['datetime']) if isinstance(attempt.get(key), dict) else None
    items = []
    for row in sorted(data['problems'], key=lambda r: r.get('ordinal') or 0):
        #older records (format 1) don't note the type: ask the problem, if it's still there
        qtype = row.get('qtype')
        if not qtype:
            vp = db.session.get(VProblem, row.get('vproblem_id')) if row.get('vproblem_id') else None
            qtype = vp.qtype if vp else 'numeric'
        cp = NS(ordinal=row.get('ordinal'), conc_prob=row.get('conc_prob'), conc_ansr=row.get('conc_ansr'),
                conc_opts=json.loads(row.get('conc_opts_json') or '{}'), submitted=row.get('submitted'),
                credit=row.get('credit'), feedback=row.get('feedback'),
                highlights=json.loads(row.get('highlights_json') or '[]'),
                vproblem=NS(qtype=qtype, image=row.get('problem_image')))
        items.append(transcript_item(cp))
    cq = NS(score=a.score, completed=a.completed, needs_review=a.needs_review,
            startdate=when('startdate'), compdate=when('compdate'), graded_date=when('graded_date'),
            vquiz=NS(title=a.quiz_title, image=data.get('quiz_image')), taker=NS(username=a.student_name))
    return Markup(render_template('transcript_body.html', cq=cq, items=items, show_answers=True))


def archive_student(user, by=None):
    """Before a student's account is deleted: keep all their attempts in the archive."""
    for cq in CQuiz.query.filter_by(assignee=user.id).order_by(CQuiz.id).all():
        archive_attempt(cq, by, 'student deleted')


def archived_attempts(subject='all'):
    """The archive, newest first; subject narrows it by the quiz's subjects."""
    q = ArchivedAttempt.query
    choice = valid_subject_choice('quizzes', subject)
    if choice == 'none':
        q = q.filter(~ArchivedAttempt.vquiz.has(VQuiz.vqgroups.any()))
    elif choice != 'all':
        q = q.filter(ArchivedAttempt.vquiz.has(VQuiz.vqgroups.any(VQGroup.id == int(choice))))
    return q.order_by(ArchivedAttempt.archived_at.desc(), ArchivedAttempt.id.desc()).all()


FOLDER_NAME_MAX = 64
UNSORTED = 'Unsorted'


def student_folder(user):
    """A student's Archive folder, made (or brought back, if the teacher deleted it) as
    needed; not committed."""
    folder = ArchiveFolder.query.filter_by(student_id=user.id).first()
    if folder is None:
        folder = ArchiveFolder(name=user.username, student_id=user.id)
        db.session.add(folder)
        db.session.flush()
    elif folder.removed:
        folder.removed, folder.name = False, user.username
    return folder


def ensure_archive_folders():
    """Every student has a folder (a new student gets one the first time the Archive is
    shown); one the teacher deleted isn't made again here."""
    from app.user.models import User
    have = {f.student_id for f in ArchiveFolder.query.filter(ArchiveFolder.student_id.isnot(None))}
    made = False
    for u in User.query.filter_by(is_admin=False):
        if u.id not in have:
            db.session.add(ArchiveFolder(name=u.username, student_id=u.id))
            made = True
    if made:
        try:
            db.session.commit()
        except IntegrityError:
            #another teacher's page made them a moment ago
            db.session.rollback()


def archive_folders():
    """The Archive page: its folders by name, each with its archived attempts (newest
    first), then Unsorted (attempts in no folder) when there are any.
    Returns [{'folder' (None for Unsorted), 'key', 'name', 'student', 'items'}]."""
    from app.user.models import User
    ensure_archive_folders()
    users = {u.id: u for u in User.query.all()}
    out = {}
    renamed = False
    for f in ArchiveFolder.query.filter_by(removed=False):
        #a student's own folder (never renamed by the teacher) follows their username
        student = users.get(f.student_id) if f.student_id else None
        if student is not None and f.name != student.username:
            f.name, renamed = student.username, True
        out[f.id] = {'folder': f, 'key': 'folder-{}'.format(f.id), 'name': f.name,
                     'student': users.get(f.student_id) if f.student_id else None, 'items': []}
    if renamed:
        db.session.commit()
    unsorted = {'folder': None, 'key': 'unsorted', 'name': UNSORTED, 'student': None, 'items': []}
    for a in ArchivedAttempt.query.order_by(ArchivedAttempt.archived_at.desc(), ArchivedAttempt.id.desc()):
        (out[a.folder_id] if a.folder_id in out else unsorted)['items'].append(a)
    folders = sorted(out.values(), key=lambda f: f['name'].lower())
    return folders + ([unsorted] if unsorted['items'] else [])


def _folder_name(name, folder=None):
    name = ' '.join((name or '').split())
    if not name:
        raise ServiceError('Please give the folder a name.')
    if len(name) > FOLDER_NAME_MAX:
        raise ServiceError('Folder names can be at most {} characters.'.format(FOLDER_NAME_MAX))
    if name.lower() == UNSORTED.lower():
        raise ServiceError('"{}" is kept for attempts that aren\'t in a folder.'.format(UNSORTED))
    for other in ArchiveFolder.query.filter_by(removed=False):
        if other is not folder and other.name.lower() == name.lower():
            raise ServiceError('There\'s already a folder called "{}".'.format(other.name))
    return name


def create_archive_folder(name):
    """A folder of the teacher's own (not tied to a student)."""
    folder = ArchiveFolder(name=_folder_name(name))
    db.session.add(folder)
    db.session.commit()
    return folder


def rename_archive_folder(folder, name):
    """Rename a folder. A student's folder becomes an ordinary folder with the new name;
    the student gets a new folder in their name for their next archived attempts."""
    new = _folder_name(name, folder)
    if new == folder.name:
        return
    folder.name = new
    folder.student_id = None
    db.session.commit()


def move_archived(ids, folder):
    """Move archived attempts to a folder (None: Unsorted). Returns how many moved."""
    wanted = _ids(ids)
    if not wanted:
        return 0
    moved = ArchivedAttempt.query.filter(ArchivedAttempt.id.in_(wanted)) \
        .update({'folder_id': folder.id if folder else None}, synchronize_session=False)
    db.session.commit()
    return moved


def delete_archive_folder(folder):
    """Delete a folder: what's in it moves to Unsorted. Returns how many moved."""
    moved = ArchivedAttempt.query.filter_by(folder_id=folder.id).update({'folder_id': None}, synchronize_session=False)
    if folder.student_id:
        #kept, so it isn't made again on its own (see ArchiveFolder)
        folder.removed = True
    else:
        db.session.delete(folder)
    db.session.commit()
    return moved


def archived_student(a):
    """The student's account, if it still exists."""
    from app.user.models import User
    return db.session.get(User, a.student_id) if a.student_id else None


def restore_blocker(a):
    """Why this archived attempt can't be put back, or None if it can."""
    if archived_student(a) is None:
        return 'Restore isn\'t possible: {}\'s account was deleted. You can still view it.'.format(a.student_name)
    vq = db.session.get(VQuiz, a.vquiz_id) if a.vquiz_id else None
    if vq is None:
        return 'Restore isn\'t possible: the quiz "{}" was deleted. You can still view it.'.format(a.quiz_title)
    data = json.loads(a.data)
    missing = [p['vproblem_id'] for p in data['problems'] if db.session.get(VProblem, p['vproblem_id']) is None]
    if missing:
        return 'Restore isn\'t possible: {} of its problems {} deleted. You can still view it.'.format(
            len(missing), 'was' if len(missing) == 1 else 'were')
    if db.session.get(CQuiz, a.original_id) is not None:
        return 'Restore isn\'t possible: its old number is in use. You can still view it.'
    return None


def restore_attempt(a):
    """Put an archived attempt back, as it was and under the same number, so the
    student sees it again and its old links work."""
    blocker = restore_blocker(a)
    if blocker:
        raise ServiceError(blocker)
    data = json.loads(a.data)
    cq = CQuiz()
    _fill_row(cq, data['attempt'])
    cq.id = a.original_id
    #archived before this was kept, or already open: no "it's open now" notice for it
    if 'open_notice_sent' not in data['attempt'] or not cq.not_open_yet():
        cq.open_notice_sent = True
    db.session.add(cq)
    db.session.flush()
    for row in data['problems']:
        cp = CProblem()
        _fill_row(cp, row)
        cp.cquiz_id = cq.id
        #question rows aren't linked to from anywhere; a new number is fine if the old one is taken
        if cp.id is not None and db.session.get(CProblem, cp.id) is not None:
            cp.id = None
        db.session.add(cp)
    db.session.delete(a)
    db.session.commit()
    return cq


def purge_archived(a):
    """Delete an archived attempt for good."""
    db.session.delete(a)
    db.session.commit()


def archived_using_quiz(vq):
    return ArchivedAttempt.query.filter_by(vquiz_id=vq.id).count()


def archived_using_problem(vp):
    return ArchivedAttempt.query.filter(ArchivedAttempt.problem_ids.like('%,{},%'.format(int(vp.id)))).count()


def archived_counts():
    """How many archived attempts use each quiz and each problem: ({quiz id: n}, {problem id: n})."""
    quizzes, problems = {}, {}
    for vquiz_id, ids in ArchivedAttempt.query.with_entities(ArchivedAttempt.vquiz_id, ArchivedAttempt.problem_ids):
        if vquiz_id:
            quizzes[vquiz_id] = quizzes.get(vquiz_id, 0) + 1
        for pid in {int(x) for x in (ids or '').split(',') if x.strip().isdigit()}:
            problems[pid] = problems.get(pid, 0) + 1
    return quizzes, problems


def archive_warning(count, what):
    """For the delete question of a quiz or problem that archived attempts use."""
    if not count:
        return ''
    return ' {} archived attempt{} use{} this {}; after deleting it {} can still be viewed but not restored.'.format(
        count, '' if count == 1 else 's', 's' if count == 1 else '', what, 'it' if count == 1 else 'they')


def retake_overrides(vq):
    """Students whose attempts at this quiz combine by their own rule instead of the
    quiz's: [(student, rule key)], by name."""
    seen = {}
    for cq in vq.cquizzes:
        if cq.own_retake_rule and cq.taker and cq.assignee not in seen:
            seen[cq.assignee] = (cq.taker, cq.own_retake_rule)
    return sorted(seen.values(), key=lambda pair: pair[0].username.lower())


def set_retake_rule(cq, rule):
    """How this student's attempts at this quiz combine; None = the quiz's own rule."""
    if rule and rule not in RETAKE_RULES:
        raise ServiceError('Unknown retake rule "{}".'.format(rule))
    #the same as the quiz's is no rule of their own: they follow the quiz's
    if rule == cq.vquiz.retake_rule:
        rule = None
    #kept on every attempt so it survives deleting one
    for other in CQuiz.query.filter_by(assignee=cq.assignee, vquiz_id=cq.vquiz_id):
        other.retake_rule = rule or None
    db.session.commit()


# ---------------------------------------------------------------- taking

def attempt_state(cq, now=None):
    """'completed', 'review' (waiting for a teacher), 'not_open', 'time_up' or 'open'."""
    now = now or datetime.now()
    if cq.completed:
        return 'completed'
    if cq.needs_review:
        return 'review'
    if cq.not_open_yet(now):
        return 'not_open'
    deadline = cq.deadline()
    if deadline and now > deadline + tuning.grace():
        return 'time_up'
    return 'open'


def close_expired(now=None):
    """Hand in and score every attempt whose time is up, even if the student never
    comes back. Returns how many were closed. Called by the app about once a
    minute (see app/__init__.py) and by `flask close-expired`."""
    now = now or datetime.now()
    candidates = CQuiz.query.filter(CQuiz.completed.is_(False), CQuiz.needs_review.is_(False),
                                    db.or_(CQuiz.closes_at.isnot(None),
                                           db.and_(CQuiz.time_limit.isnot(None), CQuiz.startdate.isnot(None)))).all()
    closed = 0
    for cq in candidates:
        if attempt_state(cq, now) == 'time_up':
            #the student may be away: a notice tells them it was handed in, why, and how it went
            started = bool(cq.startdate)
            why = 'it closed' if cq.closes_at and now >= cq.closes_at else 'your time ran out'
            outcome = submit(cq, timed_out=True)
            result = 'Your teacher will grade the written answers.' if outcome == 'review' \
                else 'Your score: {:.0f}%.'.format(cq.score or 0)
            if started:
                text = '"{}" was handed in automatically because {}, with the answers you had saved. {}'.format(
                    cq.vquiz.title, why, result)
            else:
                text = '"{}" closed before you started it, so it was handed in with no answers. {}'.format(cq.vquiz.title, result)
            notify(cq.assignee, text, _link('qgen.qtake', cidx=cq.id))
            closed += 1
    db.session.commit()
    return closed


def announce_opened(now=None, student_id=None):
    """Tell each student whose quiz had a future start time that it's open now (a
    notice, which pops up if they're on the site). Once per attempt, even with several
    server processes; not for a quiz already closed again, handed in, or started.
    Returns how many were told. Run with close_expired (about once a minute), and for
    one student (student_id) when their page checks in, so the notice arrives together
    with the page showing the quiz as open."""
    now = now or datetime.now()
    due = CQuiz.query.filter(CQuiz.open_notice_sent.is_(False), CQuiz.opens_at.isnot(None), CQuiz.opens_at <= now)
    if student_id is not None:
        due = due.filter(CQuiz.assignee == student_id)
    due = due.all()
    told = 0
    for cq in due:
        #claim it: only one process gets rowcount 1
        claimed = db.session.execute(db.update(CQuiz).where(CQuiz.id == cq.id, CQuiz.open_notice_sent.is_(False))
                                     .values(open_notice_sent=True)).rowcount
        if claimed != 1 or attempt_state(cq, now) != 'open' or cq.startdate:
            continue
        closes = ' It closes {}.'.format(cq.closes_at.strftime('%b %d at %I:%M %p')) if cq.closes_at else ''
        notify(cq.assignee, '"{}" is open now. You can start it.{}'.format(cq.vquiz.title, closes),
               _link('qgen.qtake', cidx=cq.id))
        told += 1
    db.session.commit()
    return told


def start(cq):
    """The student opened the quiz: the time limit starts now."""
    if not cq.startdate:
        cq.startdate = datetime.now()
        cq.save()


def _answers_by_ordinal(cq, answers):
    """Only answers to this quiz's questions; keys may be ints or strings."""
    by_ordinal = {cp.ordinal: cp for cp in cq.cproblems}
    out = {}
    for key, value in (answers or {}).items():
        try:
            ordinal = int(key)
        except (TypeError, ValueError):
            raise ServiceError('"{}" isn\'t a question number.'.format(key))
        if ordinal not in by_ordinal:
            raise ServiceError('This quiz has no question {}.'.format(ordinal))
        out[ordinal] = value
    return out


def autosave(cq, answers):
    """Save answers so far without handing in. answers: {question number: answer}."""
    state = attempt_state(cq)
    if state in ('completed', 'review'):
        raise ServiceError('This quiz has already been submitted.')
    if state == 'not_open':
        raise ServiceError('This quiz isn\'t open yet.')
    if state == 'time_up':
        raise ServiceError('Time is up.')
    start(cq)
    for ordinal, value in _answers_by_ordinal(cq, answers).items():
        cp = next(c for c in cq.cproblems if c.ordinal == ordinal)
        cp.submitted = get_qtype(cp.vproblem.qtype).to_stored(value)
    db.session.commit()


def submit(cq, answers=None, timed_out=False):
    """Hand in: grade what can be graded now. With answers=None (time ran out),
    the autosaved answers are used. timed_out: handed in by the app because time ran
    out (the teachers' notice says so). Returns 'completed' or 'review'."""
    if attempt_state(cq) in ('completed', 'review'):
        raise ServiceError('This quiz has already been submitted.')
    if attempt_state(cq) == 'not_open':
        raise ServiceError('This quiz isn\'t open yet.')
    if answers is not None:
        answers = _answers_by_ordinal(cq, answers)
    who = cq.taker.username if cq.taker else 'A student'
    #what the teachers' notice says happened
    said = '{} handed in "{}"'.format(who, cq.vquiz.title)
    if timed_out:
        reason = 'it closed' if cq.closes_at and datetime.now() >= cq.closes_at else 'time ran out'
        said = ('{}\'s "{}" was handed in automatically ({})' if cq.startdate else
                '{} never started "{}"; it was handed in automatically ({})').format(who, cq.vquiz.title, reason)
    if record_answers(cq, answers):
        cq.needs_review = True
        notify_teachers(cq.assignee, '{}: written answers are waiting for grading.'.format(said),
                        _link('qgen.review', cqid=cq.id))
        cq.save()
        return 'review'
    finalize(cq)
    #"Open" goes to this attempt's results (answers and score)
    notify_teachers(cq.assignee, '{}: {:.0f}%.'.format(said, cq.score or 0),
                    _link('qgen.qtake', cidx=cq.id))
    cq.save()
    return 'completed'


def _link(endpoint, **values):
    """A page address for a notice, or None outside a web request (e.g. `flask close-expired`)."""
    try:
        return url_for(endpoint, **values)
    except RuntimeError:
        return None


# ---------------------------------------------------------------- grading

def essays(cq):
    return [cp for cp in cq.cproblems if not get_qtype(cp.vproblem.qtype).auto_graded]


def grade_essays(cq, grades, finish=False, grader_id=None):
    """grades: {cproblem id: {'credit': 0-100 or None, 'feedback': str, 'highlights': [[start, end, 'right'|'wrong'], ...]}}.
    Saves them; with finish=True also closes the quiz and tells the student.
    Returns the question numbers still needing a credit (nothing is finished then)."""
    if cq.completed:
        raise ServiceError('That quiz has already been graded.')
    if not cq.needs_review:
        raise ServiceError('That quiz hasn\'t been submitted yet.')
    by_id = {cp.id: cp for cp in essays(cq)}
    for cpid, g in (grades or {}).items():
        cp = by_id.get(int(cpid))
        if not cp:
            raise ServiceError('Answer {} isn\'t a written answer in this quiz.'.format(cpid))
        if 'credit' in g:
            credit = g['credit']
            if credit is not None and not 0 <= float(credit) <= 100:
                raise ServiceError('Credit must be between 0 and 100.')
            cp.credit = None if credit is None else float(credit) / 100.0
        if 'feedback' in g:
            cp.feedback = (g['feedback'] or '').strip() or None
        if 'highlights' in g:
            spans = []
            for s in g['highlights'] or []:
                try:
                    if s[2] in ('right', 'wrong'):
                        spans.append([int(s[0]), int(s[1]), s[2]])
                except (TypeError, ValueError, IndexError):
                    continue
            cp.highlights = spans
    if not finish:
        db.session.commit()
        return []
    ungraded = [cp.ordinal for cp in by_id.values() if cp.credit is None]
    if ungraded:
        db.session.commit()
        return sorted(ungraded)
    cq.graded_by = grader_id
    cq.graded_date = datetime.now()
    finalize(cq)
    notify(cq.assignee, 'Your written answers in "{}" have been graded: {:.0f}%.'.format(cq.vquiz.title, cq.score),
           url_for('qgen.qtake', cidx=cq.id))
    cq.save()
    return []
