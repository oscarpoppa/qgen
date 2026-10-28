"""What teachers and students can do with quizzes, independent of how they ask.

The web pages (routes.py) and the REST API (app/api) both call these
functions, so grading, randomizing and the rules around them can never
drift apart. Nothing here reads the request, flashes messages or renders
pages; problems are reported by raising ServiceError (worded for people)
or by returning lists of plain-language errors.
"""
import json
import copy
import random
import uuid
from datetime import datetime

from flask import url_for, render_template
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError

from app import db, tuning
from app.messages.models import notify, notify_teachers
from . import layout
from .formfact import record_answers, finalize, TRANSCRIPT_V2
from .friendly import FriendlyError
from .models import UploadFile, PicGroup, FileGroup
from .models import CQuiz, VQuiz, VProblem, CProblem, VPGroup, VQGroup, ArchivedAttempt, ArchiveFolder, RETAKE_RULES, \
    vproblem_vpgroup, vquiz_vqgroup
from .qtypes import get_qtype

#answers are still accepted a little after the deadline (slow connections, the
#auto-submit): "Grace after a quiz's time is up" in Technical settings (app/tuning.py)


class ServiceError(ValueError):
    """Something that was asked for can't be done, worded for people to read."""


def _when(d):
    """A date in notices, written the way the site writes every date ("Fri Oct 9, 4:22 PM")."""
    from app import when_filter
    return when_filter(d)


# ---------------------------------------------------------------- subjects

#a teacher's own subjects for sorting problems and quizzes (separate lists; an item can
#be in several, or none). Stored in the old VPGroup / VQGroup tables. Not the "2 of
#these 6" question groups inside a quiz (layout.py).
SUBJECT_KINDS = {'problems': (VPGroup, VProblem, 'vpgroups', 'vproblems'),
                 'quizzes': (VQGroup, VQuiz, 'vqgroups', 'vquizzes'),
                 #(uploaded pictures and other files, in folders too: the owner, 2026-10-19)
                 'pictures': (PicGroup, UploadFile, 'picgroups', 'uploads'),
                 'files': (FileGroup, UploadFile, 'filegroups', 'uploads')}
#what one thing of each kind is called, and several
ITEM_WORDS = {'problems': ('problem', 'problems'), 'quizzes': ('quiz', 'quizzes'),
              'pictures': ('picture', 'pictures'), 'files': ('file', 'files')}
UPLOAD_KINDS = ('pictures', 'files')


def item_word(kind, n=1):
    one, many = ITEM_WORDS.get(kind, ('thing', 'things'))
    return one if n == 1 else many


def subject_kind(kind):
    if kind not in SUBJECT_KINDS:
        raise ServiceError('Unknown kind of folder “{}”.'.format(kind))
    return SUBJECT_KINDS[kind]


def subjects(kind):
    """The subjects of one kind, by name."""
    group_cls = subject_kind(kind)[0]
    return sorted(group_cls.query.all(), key=lambda g: (g.title or '').lower())


def _subject_name(kind, name, subject=None):
    name = ' '.join((name or '').split())
    if not name:
        raise ServiceError('Please give the folder a name.')
    if len(name) > tuning.get('folder_name'):
        raise ServiceError('Folder names can be at most {} characters.'.format(tuning.get('folder_name')))
    for other in subjects(kind):
        if other is not subject and (other.title or '').lower() == name.lower():
            raise ServiceError('There\'s already a folder called “{}”.'.format(other.title))
    return name


def create_subject(kind, name, parent=None):
    """A new folder, at the top or inside `parent` (a folder of the same kind)."""
    from app import folder_tree
    group_cls = subject_kind(kind)[0]
    try:
        folder_tree.check_new(group_cls, parent)
    except folder_tree.FolderError as exc:
        raise ServiceError(str(exc))
    subject = group_cls(title=_subject_name(kind, name), parent_id=parent.id if parent else None)
    db.session.add(subject)
    _commit_subject()
    return subject


def move_subject(kind, subject, target):
    """Put a folder inside another (None: at the top); never inside itself."""
    from app import folder_tree
    try:
        folder_tree.check_move(subject_kind(kind)[0], subject, target)
    except folder_tree.FolderError as exc:
        raise ServiceError(str(exc))
    subject.parent_id = target.id if target else None
    db.session.commit()


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


def delete_subject(subject, kind=None):
    """Remove a folder; nothing in it is deleted: its problems (or quizzes) and folders move
    up a level (from the top level, things in no other folder are then in no folder)."""
    group_cls, _item_cls, rel, back = subject_kind(kind or ('problems' if isinstance(subject, VPGroup) else 'quizzes'))
    up = db.session.get(group_cls, subject.parent_id) if subject.parent_id else None
    group_cls.query.filter_by(parent_id=subject.id).update({'parent_id': up.id if up else None}, synchronize_session=False)
    if up is not None:
        for item in list(getattr(subject, back)):
            if up not in getattr(item, rel):
                getattr(item, rel).append(up)
    db.session.delete(subject)
    db.session.commit()


def subject_subtree(kind, subject):
    """A folder and every folder inside it, the deepest first."""
    group_cls = subject_kind(kind)[0]
    out, todo = [], [subject]
    while todo:
        g = todo.pop()
        out.append(g)
        todo.extend(group_cls.query.filter_by(parent_id=g.id).all())
    return list(reversed(out))


def purge_plan(kind, subject):
    """What deleting a folder with everything in it would do: {'delete': [items deleted for
    good], 'remove': [quizzes removed, students keep their copies], 'keep': [(item, why)]
    (these stay and move up a level), 'folders': how many folders go}."""
    _g, _cls, rel, back = subject_kind(kind)
    tree = subject_subtree(kind, subject)
    inside_ids = {g.id for g in tree}
    items, seen = [], set()
    for g in tree:
        for item in getattr(g, back):
            if getattr(item, 'removed_at', None) and kind == 'problems':
                continue  # (taken off the Problems page: not counted, nothing to do)
            if item.id not in seen:
                seen.add(item.id)
                items.append(item)
    plan = {'delete': [], 'remove': [], 'keep': [], 'folders': len(tree)}
    for item in sorted(items, key=lambda i: (i.title or '').lower()):
        other = [g.title for g in getattr(item, rel) if g.id not in inside_ids]
        if other:
            plan['keep'].append((item, 'also in “{}”'.format(other[0])))
        elif kind == 'problems':
            if item.vquizzes:
                plan['keep'].append((item, 'used by “{}”'.format(item.vquizzes[0].title)))
            elif item.cproblems:
                plan['keep'].append((item, 'students’ answers on record'))
            else:
                plan['delete'].append(item)
        elif being_taken(item):
            plan['keep'].append((item, 'someone is taking it'))
        elif item.removed_at:
            continue  # already off the Quizzes page
        else:
            plan['remove' if item.cquizzes else 'delete'].append(item)
    return plan


def purge_question(kind, subject):
    """The warning before deleting a folder with everything in it."""
    plan = purge_plan(kind, subject)
    unit, units = ITEM_WORDS[kind]
    def n(count, one=unit, many=units):
        return '{} {}'.format(count, one if count == 1 else many)
    inner = plan['folders'] - 1
    parts = ['Delete the folder “{}”{} and what’s in it? This can’t be undone.'.format(
        subject.title, ' and the {} inside it'.format(n(inner, 'folder', 'folders')) if inner else '')]
    if plan['delete']:
        parts.append('{} deleted for good.'.format(n(len(plan['delete'])) + (' is' if len(plan['delete']) == 1 else ' are')))
    if plan['remove']:
        parts.append('{} taken off the Quizzes page; students keep their copies and scores (bring {} back from '
                     'Removed quizzes).'.format(n(len(plan['remove'])) + (' is' if len(plan['remove']) == 1 else ' are'),
                                                'it' if len(plan['remove']) == 1 else 'them'))
    if plan['keep']:
        parts.append('Kept, moving up a level: {}.'.format('; '.join('“{}” ({})'.format(i.title, why) for i, why in plan['keep'])))
    if not (plan['delete'] or plan['remove'] or plan['keep']):
        parts.append('It’s empty.')
    return ' '.join(parts)


def delete_subject_and_contents(kind, subject):
    """Delete a folder, the folders inside it and what's in them (as purge_plan says);
    returns the plan that was carried out."""
    plan = purge_plan(kind, subject)
    for item in plan['delete']:
        if kind == 'problems':
            delete_problem(item)
        else:
            delete_vquiz(item)
    for item in plan['remove']:
        delete_vquiz(item)
    for g in subject_subtree(kind, subject):
        delete_subject(g, kind)  # what's kept moves up a level
    return plan


def file_one(kind, item_id, subject, add=True, moving_from=None):
    """Put one problem (or quiz) in a folder (it stays in its others), or take it out; with
    moving_from, out of that folder at the same time (a drag from one folder to another).
    Returns the item."""
    _group_cls, item_cls, rel, _back = subject_kind(kind)
    try:
        item = db.session.get(item_cls, int(item_id))
    except (TypeError, ValueError):
        item = None
    if item is None:
        raise ServiceError('That {} doesn\'t exist any more.'.format(item_word(kind)))
    current = getattr(item, rel)
    if add and subject not in current:
        current.append(subject)
    elif not add and subject in current:
        current.remove(subject)
    if moving_from is not None and moving_from is not subject:
        #out of the folder it was dragged from only: its copies in other folders, inside it too, stay (the owner, 2026-10-27)
        if moving_from in current:
            current.remove(moving_from)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return item


def in_use(kind):
    """The problems or quizzes not removed (the ones the Problems and Quizzes pages, the quiz
    builder and Assign offer)."""
    item_cls = subject_kind(kind)[1]
    if kind in UPLOAD_KINDS:
        #(uploads: the pictures or the other files. Kept in step with the folder by uploads.sync(),
        #called where files change and when their pages open, never here: this runs inside other
        #requests, and a sync commits)
        return item_cls.query.filter(item_cls.picture.is_(kind == 'pictures'), item_cls.removed_at.is_(None))
    return item_cls.query.filter(item_cls.removed_at.is_(None))


def removed_quizzes():
    """Quizzes taken off the Quizzes page, the latest removed first."""
    return VQuiz.query.filter(VQuiz.removed_at.isnot(None)).order_by(VQuiz.removed_at.desc()).all()


def subject_tree(kind, items=None):
    """The folders as a tree (app/folder_tree.py) with their problems (or quizzes), newest
    first: (root, flat, nodes). items can also be attempts_by_quiz() groups (by their quiz)."""
    from app import folder_tree
    group_cls, item_cls, rel, _back = subject_kind(kind)
    table = getattr(item_cls, rel).property.secondary
    cols = list(table.c)
    homes = {}
    for item_id, group_id in db.session.query(cols[0], cols[1]):
        homes.setdefault(item_id, []).append(group_id)
    if items is None:
        items = in_use(kind).order_by(*upload_order(kind) if kind in UPLOAD_KINDS else (item_cls.id.desc(),)).all()
    key = (lambda g: g['vquiz'].id) if items and isinstance(items[0], dict) else (lambda item: item.id)
    return folder_tree.tree(subjects(kind), lambda g: g.title, items, homes, key=key)


def upload_order(kind):
    """Pictures and other files A to Z by name, whatever case (the owner, 2026-10-17)."""
    return (db.func.lower(UploadFile.name),)


def subject_ancestors(kind):
    """{folder id: the ids of it and the folders it's in}: something in a folder is also
    under the folders above it (the Assign page's Folder menu)."""
    group_cls = subject_kind(kind)[0]
    parent = {g.id: g.parent_id for g in group_cls.query.all()}
    out = {}
    for gid in parent:
        chain, up = [], gid
        while up is not None and up not in chain:
            chain.append(up)
            up = parent.get(up)
        out[gid] = chain
    return out


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


def move_items(kind, item_ids, subject, from_id=None):
    """Move several problems (or quizzes) into one folder. A move never touches the copies in other folders (the owner,
    2026-10-27): each leaves only the folder it's moved from (from_id, the folder open), else the one folder it's in; one
    in several folders with none of them open is put in the new folder and keeps the others (named in kept). Returns
    (how many changed, kept titles)."""
    _group_cls, item_cls, rel, _back = subject_kind(kind)
    ids = _ids(item_ids)
    changed, kept = 0, []
    for item in item_cls.query.filter(item_cls.id.in_(ids)).all() if ids else []:
        current = getattr(item, rel)
        have = [g.id for g in current]
        src = from_id if from_id in have else (have[0] if len(have) == 1 else None)
        if src is None and len(have) > 1:
            kept.append(item.title)
        moved = False
        if src is not None and src != subject.id:
            current.remove(next(g for g in current if g.id == src))
            moved = True
        if subject not in current:
            current.append(subject)
            moved = True
        changed += moved
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return changed, kept


def subject_choices(kind):
    """The folder menu: [(value, label, count)] for All, Uncategorized, then each folder (indented
    under the one it's in; counted with the folders inside it): Uncategorized right after All, like
    the side lists (the owner, 2026-10-22; it was last)."""
    _group_cls, item_cls, rel, back = subject_kind(kind)
    _root, flat, counted = subject_tree(kind)
    out = [('all', 'All ' + kind, in_use(kind).count())]  # "All quizzes", like the tabs
    out.append(('none', 'Uncategorized', in_use(kind).filter(~getattr(item_cls, rel).any()).count()))
    for g, d in flat:
        out.append((str(g.id), '\u00a0\u00a0\u00a0' * (d - 1) + g.title, counted[g.id]['count']))
    return out


def new_subject_name_error(kind, name):
    """For the "or make a new subject" box on the edit forms: a problem with the name,
    or None. A name that is already a subject (in any case) is fine: that one is used."""
    name = ' '.join((name or '').split())
    if name and len(name) > tuning.get('folder_name'):
        return 'Folder names can be at most {} characters.'.format(tuning.get('folder_name'))
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
        #made by someone else a moment ago (two folder drops at once); any other reason (a name
        #too long...) is said as it is, not lost in a search that finds nothing (code critic, 2026-10-20)
        made = next((g for g in subjects(kind) if (g.title or '').lower() == name.lower()), None)
        if made is None:
            raise
        return made


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
        errors = ['Students have already been given this problem as “{}”, so its question type can\'t change. '
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
        return 'Problem “{}” is used by these quizzes: {}.'.format(
            vp.title, ', '.join('“{}”'.format(q.title) for q in vp.vquizzes))
    if vp.cproblems:
        #students' answers to it are part of their records
        return ('Problem “{}” has {} student answer{} on record. You can take it out of quizzes instead; '
                'it just won\'t be used again.'.format(vp.title, len(vp.cproblems), '' if len(vp.cproblems) == 1 else 's'))
    return None


def own_problems(vq):
    """A quiz's problems no other quiz uses: the ones that can go with it (the owner, 2026-10-26)."""
    return [p for p in vq.vproblems if all(q.id == vq.id for q in p.vquizzes)]


def take_problems_along(problems, delete=False):
    """A quiz's own problems, gone with it: to the Trash, or (delete) deleted for good, one with students' answers kept
    quietly as delete_problem does. Returns how many."""
    for p in problems:
        if delete:
            delete_problem(p)
        else:
            archive_problem(p)
    return len(problems)


def problem_in_quiz_blocker(vp):
    """Why a problem's trash can is grayed on the Problems page (a quiz uses it), or None: nothing goes to the Trash
    while something still uses it, site-wide (the owner, 2026-10-26)."""
    if vp.vquizzes:
        return 'Problem “{}” is used by these quizzes: {}. Take it out of them first.'.format(
            vp.title or 'Untitled', ', '.join('“{}”'.format(q.title) for q in sorted(vp.vquizzes, key=lambda q: (q.title or '').lower())))
    return None


def delete_problem(vp):
    """A problem's Delete for good. While a quiz uses it or students answered it, it can't go:
    it's kept for those, quietly taken off the Problems page and the quiz builder's list (the
    owner, 2026-10-13). Returns 'deleted' or 'removed'."""
    if problem_delete_blocker(vp):
        vp.removed_at = datetime.now()
        vp.vpgroups = []  # (out of sight: in no folder either)
        db.session.commit()
        return 'removed'
    db.session.delete(vp)
    db.session.commit()
    return 'deleted'


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
                raise ServiceError('Problem “{}” couldn\'t be set up; please open it and check it.'.format(vprob.title))


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

QUIZ_SETTINGS = ('image', 'calculator_ok', 'shuffle_order', 'retake_rule')


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


def quiz_name_taken(title, except_id=None):
    """The quiz in use (not in the Archive) already called this, ignoring capitals and extra
    spaces, or None: two quizzes may not share a name (the owner, 2026-10-19)."""
    want = ' '.join((title or '').split()).lower()
    if not want:
        return None
    for vq in in_use('quizzes').all():
        if vq.id != except_id and ' '.join((vq.title or '').split()).lower() == want:
            return vq
    return None


QUIZ_NAME_TAKEN = 'There’s already a quiz called “{}”. Please give this one a different name.'


def save_vquiz(vq, title, problems, author_id=None, **settings):
    """Check and save a quiz (new or existing). Returns errors; saves only if there are none."""
    lay, errors = check_layout(problems)
    if not (title or '').strip():
        errors = ['Please give the quiz a title.'] + errors
    elif quiz_name_taken(title, vq.id):
        errors = [QUIZ_NAME_TAKEN.format(' '.join(title.split()))] + errors
    if settings.get('retake_rule') and settings['retake_rule'] not in RETAKE_RULES:
        errors.append('Unknown retake rule “{}”.'.format(settings['retake_rule']))
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
            setattr(vq, key, settings[key])
    vq.vpid_lst = layout.dumps(lay)
    vq.vproblems = [db.session.get(VProblem, a) for a in set(layout.all_ids(lay))]
    vq.save()
    return []


def being_taken(vq, now=None):
    """Its tries someone is in the middle of: started, not handed in, and still open (its due
    date or time limit hasn't run out)."""
    now = now or datetime.now()
    #(and its student active on the site lately: one started days ago and left counts no more, so it can't block the
    #quiz's trash can forever; the owner, 2026-10-26, Technical setting "Still taking a quiz for")
    from datetime import timedelta
    from app import tuning
    since = now - timedelta(hours=tuning.get('taking_hours'))
    return [cq for cq in vq.cquizzes if cq.startdate and not cq.completed and not cq.needs_review
            and not (cq.deadline() and cq.deadline() <= now)
            and cq.taker is not None and cq.taker.last_seen is not None and cq.taker.last_seen >= since]


def files_in_use():
    """{file name: ([problem titles], [quiz titles])} for every uploaded file a problem or quiz uses (its picture, a
    problem's pictures), in the Trash too (they can be restored); worked out once a request."""
    from flask import g, has_request_context
    if has_request_context() and getattr(g, 'files_in_use', None) is not None:
        return g.files_in_use
    out = {}
    for title, image, opts in VProblem.query.with_entities(VProblem.title, VProblem.image, VProblem.options_json):
        names = {image} if image else set()
        try:
            names |= {i.get('file') for i in (json.loads(opts or '{}').get('images') or []) if isinstance(i, dict) and i.get('file')}
        except (TypeError, ValueError):
            pass
        for n in names:
            out.setdefault(n, ([], []))[0].append(title or 'Untitled')
    for title, image in VQuiz.query.with_entities(VQuiz.title, VQuiz.image):
        if image:
            out.setdefault(image, ([], []))[1].append(title or 'Untitled')
    if has_request_context():
        g.files_in_use = out
    return out


def file_delete_blocker(name, kind='pictures'):
    """Why an uploaded file can't be deleted for good (a problem or quiz uses it), or None (the owner, 2026-10-26: like
    a problem's, its Delete grayed with this, and refused)."""
    #(nor the site's logo or tab picture, chosen in Settings: the code critic, 2026-10-26)
    from .models import Setting
    if name and name in (Setting.get('logo'), Setting.get('favicon')):
        return '{} “{}” is the site’s logo or tab picture. Choose another in Settings first.'.format(
            'Picture' if kind == 'pictures' else 'File', name)
    problems, quizzes = files_in_use().get(name, ([], []))
    if not (problems or quizzes):
        return None
    def names(titles):
        shown = ', '.join('“{}”'.format(t) for t in sorted(titles)[:5])
        return shown + (' and {} more'.format(len(titles) - 5) if len(titles) > 5 else '')
    parts = (['these problems: ' + names(problems)] if problems else []) + (['these quizzes: ' + names(quizzes)] if quizzes else [])
    return '{} “{}” is used by {}. Take it out of them first.'.format(
        'Picture' if kind == 'pictures' else 'File', name, '; and '.join(parts))


def vquiz_delete_blocker(vq):
    """Why the quiz can't be taken off the Quizzes page right now, or None."""
    busy = being_taken(vq)
    if busy:
        names = sorted({cq.taker.shown_name for cq in busy if cq.taker})
        return '{} {} taking “{}” right now. Try again once it’s handed in (or its time runs out).'.format(
            ' and '.join(names) or 'Someone', 'is' if len(names) <= 1 else 'are', vq.title)
    return None


def copy_item(kind, item, title, author):
    """A copy of a problem or quiz (a row's Copy icon and its dialog, the owner 2026-10-16):
    everything the same but its title, in the same folders; a quiz has the same problems and
    settings. Nobody has it yet: no attempts, answers or history come along. Returns the copy."""
    from sqlalchemy import inspect as sa_inspect
    cls = type(item)
    new = cls()
    for prop in sa_inspect(cls).column_attrs:
        if prop.key in ('id', 'removed_at', 'create_date', 'author_id'):
            continue
        setattr(new, prop.key, getattr(item, prop.key))
    new.title = (title or '').strip()[:64] or item.title
    new.author_id = author.id if author is not None else None
    if kind == 'problems':
        new.vpgroups = list(item.vpgroups)
    else:
        new.vqgroups = list(item.vqgroups)
        new.vproblems = list(item.vproblems)
    db.session.add(new)
    db.session.commit()
    return new


def archive_problem(vp):
    """The trash can's Move to Archive (the owner, 2026-10-16): off the Problems page and the quiz
    builder's list, into the Archive's Problems, where it can be restored. Quizzes that use it keep
    it; it stays in its folders, for when it comes back."""
    vp.removed_at = datetime.now()
    db.session.commit()


def restore_problem(vp):
    """An archived problem back on the Problems page, in Uncategorized (out of the folders it
    was in: the owner, 2026-10-16)."""
    vp.removed_at = None
    vp.vpgroups = []
    db.session.commit()


def removed_problems():
    return VProblem.query.filter(VProblem.removed_at.isnot(None)).order_by(VProblem.removed_at.desc()).all()


def archive_vquiz(vq):
    """The trash can's Move to Archive: off the Quizzes page and Assign, into the Archive's
    Quizzes (what used to be Removed quizzes), taken or not. Students keep their copies and
    scores. Refused while someone is taking it."""
    blocker = vquiz_delete_blocker(vq)
    if blocker:
        raise ServiceError(blocker)
    vq.removed_at = datetime.now()
    db.session.commit()


def delete_vquiz(vq):
    """A quiz's Delete for good. Never taken: deleted. Once students have it, it can't go: it's
    taken off the Quizzes page into Removed quizzes (students keep their copies and scores, the
    results stay; it can be restored there or deleted for good). Returns 'deleted' or
    'removed'. Refused while someone is taking it."""
    blocker = vquiz_delete_blocker(vq)
    if blocker:
        raise ServiceError(blocker)
    if vq.cquizzes:
        vq.removed_at = datetime.now()
        db.session.commit()
        return 'removed'
    _forget_notices(['/quiz/listvq/{}'.format(vq.id)])
    db.session.delete(vq)
    db.session.commit()
    return 'deleted'


def delete_removed_vquiz(vq, by=None):
    """Delete a removed quiz for good: every student's try at it goes to the Archive first
    (readable there, not restorable), then the quiz is deleted. Refused while someone is
    taking it. Returns how many tries were archived."""
    blocker = vquiz_delete_blocker(vq)
    if blocker:
        raise ServiceError(blocker)
    tries = list(vq.cquizzes)
    for cq in tries:
        archive_attempt(cq, by)
    db.session.flush()
    _forget_notices(['/quiz/listvq/{}'.format(vq.id)])
    db.session.delete(vq)
    db.session.commit()
    return len(tries)


def bring_back_vquiz(vq):
    """A removed quiz back on the Quizzes page and Assign, in Uncategorized (the owner, 2026-10-16)."""
    vq.removed_at = None
    vq.vqgroups = []
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


# ---------------------------------------------------------------- viewing (nothing saved)

def _sample_item(vp, rng, num=None):
    """One student's version of a problem, for viewing only."""
    qt = get_qtype(vp.qtype)
    prob, ansr, opts = instantiate_problem(vp, rng)
    return {'num': num, 'vpid': vp.id, 'title': vp.title, 'qtype': qt.label, 'essay': not qt.auto_graded, 'paper': qt.paper, 'look': qt.look,
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


def quiz_varies(vq, tries=8):
    """Whether students can get different versions of this quiz: its order shuffled, a group's
    picks, or a problem whose numbers or choices change. False: every student gets the same,
    so View's "Roll another" is grayed out (the owner, 2026-10-19)."""
    try:
        entries = layout.parse(vq.vpid_lst)
    except layout.LayoutError:
        return True
    if vq.shuffle_order and layout.question_count(entries) > 1:
        return True
    ids = []
    for entry in entries:
        if layout.is_group(entry):
            if entry['pick'] < len(entry['from']):
                return True
            ids.extend(entry['from'])
        else:
            ids.append(entry)
    rng = random.Random()
    for pid in ids:
        vp = db.session.get(VProblem, pid)
        if vp is None:
            continue
        try:
            seen = {repr((it['text'], it['choices'])) for it in (_sample_item(vp, rng) for _ in range(tries))}
        except Exception:
            return True
        if len(seen) > 1:
            return True
    return False


# ---------------------------------------------------------------- assigning

def draw_quiz(vquiz, same='order', shuffle=None):
    """One drawing of a quiz to give every student alike (Assign's "Every student gets"): the
    problems picked and put in order once; with same='all', each problem's numbers and choices
    drawn once too. create_cquiz's `plan`. `shuffle`: None for the quiz's own setting."""
    ordered = layout.draw(layout.parse(vquiz.vpid_lst), random)
    if vquiz.shuffle_order if shuffle is None else shuffle:
        random.shuffle(ordered)
    if same != 'all':
        return [(pid, None) for pid in ordered]
    plan, seen = [], set()
    for pid in ordered:
        vprob = db.session.get(VProblem, pid)
        drawn = instantiate_problem(vprob)
        tries = 0
        while (pid, drawn[0]) in seen and tries < 30:
            drawn = instantiate_problem(vprob)
            tries += 1
        seen.add((pid, drawn[0]))
        plan.append((pid, drawn))
    return plan


def create_cquiz(vquiz, assignee, opens_at=None, closes_at=None, time_limit=None, plan=None, shuffle=None):
    """One student's own copy of a quiz. Raises ServiceError if it can't be made. `plan`
    (draw_quiz) gives every student the same order, or the very same problems. `shuffle`: None
    for the quiz's own setting, else this assignment's (Assign's "Keep the quiz's order")."""
    try:
        cq = CQuiz(vquiz_id=vquiz.id, assignee=assignee.id, opens_at=opens_at, closes_at=closes_at, time_limit=time_limit)
        #only a quiz that opens later gets an "it's open now" notice (see announce_opened)
        cq.open_notice_sent = not (opens_at and opens_at > datetime.now())
        cq.seen_by_taker = False  # counted next to "My quizzes" until they look
        if plan is None:
            #groups ("2 of these 6") are drawn separately for each student
            ordered = layout.draw(layout.parse(vquiz.vpid_lst), random)
            #so "question 1 is B" means nothing to the student next door
            if vquiz.shuffle_order if shuffle is None else shuffle:
                random.shuffle(ordered)
            plan = [(pid, None) for pid in ordered]
        seen = set()
        for ordinal, (pid, drawn) in enumerate(plan, 1):
            vprob = db.session.get(VProblem, pid)
            if drawn is not None:
                #the very same problem as everyone else's (its own copy of the extra data)
                prob, ansr, opts = drawn[0], drawn[1], copy.deepcopy(drawn[2])
                cp = CProblem(ordinal=ordinal, conc_prob=prob, conc_ansr=ansr, vproblem_id=vprob.id)
                cp.conc_opts = opts
                cq.cproblems.append(cp)
                continue
            prob, ansr, opts = instantiate_problem(vprob)
            #a problem used several times in a quiz: a different version each time, when its
            #values allow one (the owner, 2026-10-18)
            tries = 0
            while (pid, prob) in seen and tries < 30:
                prob, ansr, opts = instantiate_problem(vprob)
                tries += 1
            seen.add((pid, prob))
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
        raise ServiceError('Couldn\'t create “{}” for {}: {}'.format(vquiz.title, assignee.username, exc))


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


ASSIGN_NOTE_MAX = 4000


def assign(vquiz, students, opens_at=None, closes_at=None, time_limit=None, by=None, same='', keep_order=None, note=''):
    """Give each student a separate copy; returns (created quizzes, [(student, error), ...]).
    `by` is the teacher assigning it: the teachers' notices say who assigned what. `same`:
    '' each student's own version, 'order' the same problems in the same order (own numbers),
    'all' the very same quiz for everyone (the owner, 2026-10-24). `keep_order`: None for the
    quiz's own setting, True/False to keep or shuffle its order for this assignment only. `note`: the teacher's note to the
    students on it, one for everyone given it here (assign_group; the owner, 2026-10-28)."""
    shuffle = None if keep_order is None else not keep_order
    if opens_at and closes_at and closes_at <= opens_at:
        raise ServiceError('The closing time must be after the opening time.')
    if time_limit is not None and not 1 <= time_limit <= 600:
        raise ServiceError('The time limit must be between 1 and 600 minutes.')
    too_long = time_limit_error(opens_at, closes_at, time_limit)
    if too_long:
        raise ServiceError(too_long)
    created, failed = [], []
    plan = None
    group = uuid.uuid4().hex
    if same in ('order', 'all'):
        try:
            plan = draw_quiz(vquiz, same, shuffle)
        except ServiceError as exc:
            return [], [(student, str(exc)) for student in students]
    for student in students:
        try:
            cq = create_cquiz(vquiz, student, opens_at, closes_at, time_limit, plan=plan, shuffle=shuffle)
        except ServiceError as exc:
            failed.append((student, str(exc)))
            continue
        cq.assign_group = group
        if note:
            cq.assign_note, cq.assign_note_at = note, datetime.now()
        when = ' It opens {}.'.format(_when(cq.opens_at)) if cq.opens_at else ''
        notify(student.id, 'New quiz: “{}”.{}'.format(vquiz.title, when), url_for('qgen.qtake', cidx=cq.id))
        created.append(cq)
    if created:
        _notice_assigned(vquiz, created, by, opens_at, closes_at, time_limit)
    db.session.commit()
    return created, failed


def _notice_assigned(vquiz, created, by, opens_at, closes_at, time_limit):
    """One notice for the teachers per assignment (not one per student), e.g.
    'dan assigned "Quiz 3" to 3 students: sam, kim, lee. Due Oct 03 at 05:00 PM.'"""
    names = [cq.taker.shown_name for cq in created if cq.taker]
    shown = ', '.join(names[:6]) + (' and {} more'.format(len(names) - 6) if len(names) > 6 else '')
    details = []
    if opens_at:
        details.append('Opens {}.'.format(_when(opens_at)))
    if closes_at:
        details.append('Due {}.'.format(_when(closes_at)))
    if time_limit:
        details.append('{} minute time limit.'.format(time_limit))
    body = '{} assigned “{}” to {} student{}: {}.{}'.format(
        by.username if by else 'A teacher', vquiz.title, len(names), '' if len(names) == 1 else 's', shown,
        (' ' + ' '.join(details)) if details else '')
    #a notice belongs to one person's record, whose picture the panel shows: the student's when
    #it went to one; with several, the assigning teacher's (the panel shows a group icon then)
    #"Open" goes to what was assigned: one student's own copy of the quiz (for a teacher who
    #took it themselves, their results page, since opening their own copy would start it), or
    #with several students, the quiz's results page listing each one's copy
    if len(created) == 1 and created[0].taker and not created[0].taker.is_admin:
        link = _link('qgen.qtake', cidx=created[0].id)
    elif len(created) == 1:
        link = _link('qgen.list_user', uid=created[0].assignee)
    else:
        link = _link('qgen.quiz_results_page', vqid=vquiz.id)
    notify_teachers(created[0].assignee if len(created) == 1 or not by else by.id, body, link)


def retake(cq, by=None):
    """A fresh copy, with new values, of a quiz the student has taken. `by` is the
    teacher giving it: the student and the teachers each get a notice."""
    if not (cq.completed or cq.needs_review):
        raise ServiceError('{} hasn\'t finished “{}” yet.'.format(cq.taker.shown_name, cq.vquiz.title))
    new = create_cquiz(cq.vquiz, cq.taker)
    new.retake_rule = cq.retake_rule
    #(the teacher's note to the student, and its Assign group, go with it: the owner, 2026-10-28)
    new.assign_note, new.assign_note_at, new.assign_group = cq.assign_note, cq.assign_note_at, cq.assign_group
    #a quiz to take again comes out of the student's folders, back where they'll see it
    from .models import QuizPlacement
    QuizPlacement.query.filter_by(owner_id=cq.assignee, vquiz_id=cq.vquiz_id).delete(synchronize_session=False)
    notify(cq.assignee, 'You can try “{}” again.'.format(cq.vquiz.title), url_for('qgen.qtake', cidx=new.id))
    #for the teachers; "Open" goes to that student's results
    notify_teachers(cq.assignee, '{} gave {} a retake of “{}”.'.format(by.shown_name if by else 'A teacher', cq.taker.shown_name, cq.vquiz.title),
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


def take_away(student, vq, by=None):
    """Take a quiz away from a student: every try at it goes to the Archive (as one by one),
    together or not at all. Returns how many."""
    tries = [cq for cq in vq.cquizzes if cq.assignee == student.id]
    for cq in tries:
        archive_attempt(cq, by)
    db.session.commit()
    return len(tries)


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
    return Markup(render_template('transcript_body.html', cq=cq, items=items))


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


UNSORTED = 'Uncategorized'


def student_folder(user):
    """A student's Archive folder, made (or brought back, if the teacher removed it) as
    needed; not committed."""
    folder = ArchiveFolder.query.filter_by(student_id=user.id).first()
    if folder is None:
        folder = ArchiveFolder(name=user.username, student_id=user.id)
        db.session.add(folder)
        db.session.flush()
    elif folder.removed:
        folder.removed, folder.name, folder.own_name, folder.parent_id = False, user.username, False, None
    return folder


DELETED_MARK = ' (deleted)'


def _deleted_name(name, folder):
    """“ava (deleted)”, or “ava (deleted 2)” when that's taken: a deleted account's Archive folder,
    so a new account with the same name doesn't look like the same person (the owner, 2026-10-19)."""
    taken = {(f.name or '').lower() for f in ArchiveFolder.query.filter_by(removed=False) if f is not folder}
    n = 1
    while True:
        mark = DELETED_MARK if n == 1 else ' (deleted {})'.format(n)
        cand = (name or '')[:tuning.get('folder_name') - len(mark)] + mark
        if cand.lower() not in taken:
            return cand
        n += 1


def mark_deleted_folder(user):
    """The Archive folder of an account about to be deleted gets “ (deleted)” on its name, unless
    the teacher gave it a name of its own. Not committed."""
    f = ArchiveFolder.query.filter_by(student_id=user.id).first()
    if f is None:
        return
    if not f.own_name and '(deleted' not in (f.name or ''):
        f.name = _deleted_name(f.name, f)
    #(tied to no one from now on, whatever the database does on the delete: a new account can
    #never take it over)
    f.student_id = None


def ensure_archive_folders():
    """Every student has a folder (a new student gets one the first time the Archive is
    shown); one the teacher removed isn't made again here. A student's folder follows their
    username, unless the teacher gave it a name of its own."""
    from app.user.models import User
    folders = {f.student_id: f for f in ArchiveFolder.query.filter(ArchiveFolder.student_id.isnot(None))}
    changed = False
    for u in User.query.filter_by(is_admin=False):
        f = folders.get(u.id)
        if f is None:
            db.session.add(ArchiveFolder(name=u.username, student_id=u.id))
            changed = True
        elif not f.own_name and not f.removed and f.name != u.username:
            f.name, changed = u.username, True
    #(old folders from before folders were tied to students: one with a student's name, holding
    #only that student's attempts and no folders, is merged into the student's own folder, so the
    #Archive doesn't show "ava" twice: the owner, 2026-10-19)
    by_id = {f.student_id: f for f in ArchiveFolder.query.filter(ArchiveFolder.student_id.isnot(None))}
    names = {}
    for sid, f in by_id.items():
        if not f.removed:
            names.setdefault((f.name or '').lower(), []).append(f)
    #(never a folder the teacher named or removed: those are the teacher's own, found by the code
    #critic, 2026-10-20)
    for old in ArchiveFolder.query.filter(ArchiveFolder.student_id.is_(None), ArchiveFolder.own_name.is_(False),
                                          ArchiveFolder.removed.is_(False)).all():
        twins = names.get((old.name or '').lower(), [])
        if len(twins) != 1 or ArchiveFolder.query.filter_by(parent_id=old.id).first() is not None:
            continue
        home = twins[0]
        inside = ArchivedAttempt.query.filter_by(folder_id=old.id).all()
        if any(a.student_id != home.student_id for a in inside):
            continue
        for a in inside:
            a.folder_id = home.id
        db.session.delete(old)
        changed = True
    #(a deleted account's folder from before “ (deleted)” was added: tied to no one, named after
    #the person, holding only attempts of deleted accounts with that name: the owner, 2026-10-19)
    for old in ArchiveFolder.query.filter(ArchiveFolder.student_id.is_(None), ArchiveFolder.removed.is_(False),
                                          ArchiveFolder.own_name.is_(False)).all():
        if '(deleted' in (old.name or '') or ArchiveFolder.query.filter_by(parent_id=old.id).first() is not None:
            continue
        inside = ArchivedAttempt.query.filter_by(folder_id=old.id).all()
        if inside and all(a.student_id is None and (a.student_name or '').lower() == (old.name or '').lower() for a in inside):
            old.name = _deleted_name(old.name, old)
            changed = True
    if changed:
        try:
            db.session.commit()
        except IntegrityError:
            #another teacher's page made them a moment ago
            db.session.rollback()


def archive_tree():
    """The Archive's folders as a tree (app/folder_tree.py), each with its archived attempts
    newest first: (root, flat, nodes, every attempt)."""
    from app import folder_tree
    ensure_archive_folders()
    folders = sorted(ArchiveFolder.query.filter_by(removed=False).all(), key=lambda f: f.name.lower())
    attempts = ArchivedAttempt.query.order_by(ArchivedAttempt.archived_at.desc(), ArchivedAttempt.id.desc()).all()
    homes = {a.id: [a.folder_id] for a in attempts if a.folder_id}
    root, flat, nodes = folder_tree.tree(folders, lambda f: f.name, attempts, homes)
    return root, flat, nodes, attempts


def _folder_name(name, folder=None):
    from app import folder_tree
    try:
        name = folder_tree.clean_name(name)
    except folder_tree.FolderError as exc:
        raise ServiceError(str(exc))
    if name.lower() == UNSORTED.lower():
        raise ServiceError('“{}” is kept for attempts that aren\'t in a folder.'.format(UNSORTED))
    for other in ArchiveFolder.query.filter_by(removed=False):
        if other is not folder and other.name.lower() == name.lower():
            raise ServiceError('There\'s already a folder called “{}”.'.format(other.name))
    return name


def get_archive_folder(folder_id):
    """A folder that's there (not removed), or None."""
    try:
        f = db.session.get(ArchiveFolder, int(folder_id))
    except (TypeError, ValueError):
        return None
    return f if f is not None and not f.removed else None


def create_archive_folder(name, parent=None):
    """A folder of the teacher's own (not tied to a student), at the top or inside `parent`."""
    from app import folder_tree
    try:
        folder_tree.check_new(ArchiveFolder, parent)
    except folder_tree.FolderError as exc:
        raise ServiceError(str(exc))
    #(own_name: named by the teacher, so it's never merged into a student's folder of the same name)
    folder = ArchiveFolder(name=_folder_name(name), parent_id=parent.id if parent else None, own_name=True)
    db.session.add(folder)
    db.session.commit()
    return folder


def rename_archive_folder(folder, name):
    """Rename a folder. A student's folder stays theirs and keeps the new name."""
    new = _folder_name(name, folder)
    if new == folder.name:
        return
    folder.name = new
    if folder.student_id:
        folder.own_name = True
    db.session.commit()


def move_archive_folder(folder, target):
    """Put a folder inside another (None: at the top); never inside itself."""
    from app import folder_tree
    try:
        folder_tree.check_move(ArchiveFolder, folder, target, scope={'removed': False})
    except folder_tree.FolderError as exc:
        raise ServiceError(str(exc))
    folder.parent_id = target.id if target else None
    db.session.commit()


def move_archived(ids, folder):
    """Move archived attempts to a folder (None: uncategorized). Returns how many moved."""
    wanted = _ids(ids)
    if not wanted:
        return 0
    moved = ArchivedAttempt.query.filter(ArchivedAttempt.id.in_(wanted)) \
        .update({'folder_id': folder.id if folder else None}, synchronize_session=False)
    db.session.commit()
    return moved


def delete_archive_folder(folder):
    """Remove a folder: what's in it (attempts and folders) moves up a level. Returns how
    many attempts moved."""
    up = folder.parent_id
    moved = ArchivedAttempt.query.filter_by(folder_id=folder.id).update({'folder_id': up}, synchronize_session=False)
    ArchiveFolder.query.filter_by(parent_id=folder.id).update({'parent_id': up}, synchronize_session=False)
    if folder.student_id:
        #kept, so it isn't made again on its own (see ArchiveFolder)
        folder.removed, folder.parent_id = True, None
    else:
        db.session.delete(folder)
    db.session.commit()
    return moved


def archive_subtree(folder):
    """An Archive folder and every folder inside it, the deepest first."""
    out, todo = [], [folder]
    while todo:
        f = todo.pop()
        out.append(f)
        todo.extend(ArchiveFolder.query.filter_by(parent_id=f.id, removed=False).all())
    return list(reversed(out))


def archive_folder_count(folder):
    """How many archived attempts a folder holds, with the folders inside it."""
    ids = [f.id for f in archive_subtree(folder)]
    return ArchivedAttempt.query.filter(ArchivedAttempt.folder_id.in_(ids)).count()


def delete_archive_folder_and_contents(folder):
    """Delete a folder, the folders inside it and every archived attempt in them, for good.
    A student's folder is kept out of sight (made again when they next have an attempt
    archived). Returns how many attempts were deleted."""
    tree = archive_subtree(folder)
    gone = ArchivedAttempt.query.filter(ArchivedAttempt.folder_id.in_([f.id for f in tree])) \
        .delete(synchronize_session=False)
    for f in tree:
        if f.student_id:
            f.removed, f.parent_id = True, None
        else:
            db.session.delete(f)
        db.session.flush()
    db.session.commit()
    return gone


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
        return 'Restore isn\'t possible: the quiz “{}” was deleted. You can still view it.'.format(a.quiz_title)
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
    cq.seen_by_taker = True  # coming back isn't a new quiz
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
    return ' {} attempt{} in the Trash use{} this {}; after deleting it {} can still be viewed but not restored.'.format(
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
        raise ServiceError('Unknown retake rule “{}”.'.format(rule))
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
                text = '“{}” was handed in automatically because {}, with the answers you had saved. {}'.format(
                    cq.vquiz.title, why, result)
            else:
                text = '“{}” closed before you started it, so it was handed in with no answers. {}'.format(cq.vquiz.title, result)
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
        closes = ' It closes {}.'.format(_when(cq.closes_at)) if cq.closes_at else ''
        notify(cq.assignee, '“{}” is open now. You can start it.{}'.format(cq.vquiz.title, closes),
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
            raise ServiceError('“{}” isn\'t a question number.'.format(key))
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
    who = cq.taker.shown_name if cq.taker else 'A student'
    #what the teachers' notice says happened
    said = '{} handed in “{}”'.format(who, cq.vquiz.title)
    if timed_out:
        reason = 'it closed' if cq.closes_at and datetime.now() >= cq.closes_at else 'time ran out'
        said = ('{}\'s “{}” was handed in automatically ({})' if cq.startdate else
                '{} never started “{}”; it was handed in automatically ({})').format(who, cq.vquiz.title, reason)
    if record_answers(cq, answers, ai=not timed_out):
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
    """The answers the teacher grades: written answers, paper pages, and close Short text answers."""
    from .formfact import teacher_grades
    return [cp for cp in cq.cproblems if teacher_grades(cp)]


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
    notify(cq.assignee, 'Your written answers in “{}” have been graded: {:.0f}%.'.format(cq.vquiz.title, cq.score),
           url_for('qgen.qtake', cidx=cq.id))
    cq.save()
    return []


def change_grades(cq, grades, changer_id=None):
    """A finished attempt's grades changed by a teacher (the owner, 2026-10-25, CP9): the student's answers stay
    as they are; each graded question's credit and comment (and a written answer's highlights) can change.
    grades: as grade_essays. The score is worked out again. Returns the question numbers left without a credit
    (nothing is saved then); [] when saved."""
    from .formfact import qtype_of, quiz_score, build_transcript, TRANSCRIPT_V2
    if not cq.completed:
        raise ServiceError('That quiz hasn\'t been submitted yet.')
    by_id = {cp.id: cp for cp in cq.cproblems if not qtype_of(cp).look}
    missing, changed = [], False
    for cpid, g in (grades or {}).items():
        cp = by_id.get(int(cpid))
        if not cp:
            raise ServiceError('Answer {} isn\'t a graded answer in this quiz.'.format(cpid))
        credit = g.get('credit')
        if credit is None:
            missing.append(cp.ordinal)
            continue
        if not 0 <= float(credit) <= 100:
            raise ServiceError('Credit must be between 0 and 100.')
        if cp.credit is None or round(cp.credit * 100) != round(float(credit)):
            cp.credit = float(credit) / 100.0
            changed = True
            #the teacher's grade now, not the AI's or the automatic one
            cp.conc_opts = {k: v for k, v in cp.conc_opts.items() if k not in ('ai_right', 'to_check')}
        if 'feedback' in g and ((g['feedback'] or '').strip() or None) != cp.feedback:
            cp.feedback = (g['feedback'] or '').strip() or None
            changed = True
        if 'highlights' in g and not qtype_of(cp).auto_graded:
            spans = []
            for s in g['highlights'] or []:
                try:
                    if s[2] in ('right', 'wrong'):
                        spans.append([int(s[0]), int(s[1]), s[2]])
                except (TypeError, ValueError, IndexError):
                    continue
            if spans != cp.highlights:
                cp.highlights = spans
                changed = True
    if missing:
        db.session.rollback()
        return sorted(missing)
    if not changed:
        return []
    cq.score = quiz_score(cq)
    cq.changed_by = changer_id
    cq.changed_date = datetime.now()
    cq.transcript = TRANSCRIPT_V2 + build_transcript(cq)
    notify(cq.assignee, 'Your teacher changed the grades on “{}”: now {:.0f}%.'.format(cq.vquiz.title, cq.score),
           _link('qgen.qtake', cidx=cq.id))
    cq.save()
    return []


# ---------------------------------------------------------------- the same problem twice

def problem_key(qtype, question, answer, options):
    """What makes a problem what it is, the same for two problems that differ only in spacing
    or in what their values are called (the owner, 2026-10-18): a scanned page's 20 sums of
    two 2-digit numbers are one problem, used 20 times."""
    import re as _re
    options = options or {}
    values = [dict(v) for v in options.get('values') or []]
    names = [str(v.get('name') or '') for v in values]
    text = ' '.join([question or '', answer or '', options.get('choices') or '', options.get('combos') or ''] +
                    [str(v.get('formula') or '') for v in values])
    def first(name):
        m = _re.search(r'(?<![A-Za-z0-9_])' + _re.escape(name) + r'(?![A-Za-z0-9_])', text)
        return m.start() if m else len(text)
    order = sorted(range(len(names)), key=lambda i: (first(names[i]), i))
    rename = {names[i]: 'v{}'.format(k + 1) for k, i in enumerate(order) if names[i]}
    pattern = _re.compile(r'(?<![A-Za-z0-9_])(' + '|'.join(_re.escape(n) for n in sorted(rename, key=len, reverse=True)) + r')(?![A-Za-z0-9_])') if rename else None

    def canon(t):
        t = ' '.join(str(t or '').split())
        return pattern.sub(lambda m: rename[m.group(1)], t) if pattern else t
    vals = []
    for v in values:
        v = {k: (canon(x) if isinstance(x, str) else sorted(canon(y) for y in x) if isinstance(x, list) else x)
             for k, x in v.items() if x not in (None, '', [])}
        vals.append(v)
    vals.sort(key=lambda v: json.dumps(v, sort_keys=True))
    keep = {k: options.get(k) for k in ('precision', 'ordered', 'case_sensitive', 'show_n', 'complex', 'answer_display', 'shuffle')}
    if not (options.get('choices') or '').strip():
        keep.pop('shuffle')  # (only choices are shuffled)
    pictures = sorted(str(i.get('file') or '') for i in options.get('images') or [])
    #(a scanned problem's words as written over the page: a column sum isn't a row sum there)
    return json.dumps([qtype, canon(question), canon(answer), canon(options.get('choices')), canon(options.get('combos')),
                       vals, keep, pictures, canon(options.get('page_text'))], sort_keys=True)


def page_text_fits(page_text, values):
    """True when every [name] in a scanned problem's page wording is one of its values."""
    import re as _re
    names = {str(v.get('name') or '') for v in values}
    used = set(_re.findall(r'[A-Za-z_][A-Za-z0-9_]*', ' '.join(_re.findall(r'\[([^\]]*)\]', page_text or ''))))
    return bool(used) and used <= names


def same_problem(qtype, question, answer, options, author_id=None):
    """A problem already in the library that is the same as this one (problem_key), or None. (Each library problem's
    key is worked out once per request, kept by its id: a workbook page asks this for every problem on it, and worked
    out again each time it took most of the page's 0.3 s; a problem made meanwhile is still looked at. 2026-10-25)"""
    from flask import g, has_app_context
    key = problem_key(qtype, question, answer, options)
    known = g.setdefault('problem_keys', {}) if has_app_context() else {}
    ids = [i for (i,) in in_use('problems').filter(VProblem.qtype == qtype).with_entities(VProblem.id).order_by(VProblem.id).all()]
    todo = [i for i in ids if i not in known]
    if todo:
        for vp in VProblem.query.filter(VProblem.id.in_(todo)).all():
            known[vp.id] = problem_key(vp.qtype, vp.raw_prob, vp.raw_ansr, vp.options)
    for i in ids:
        if known.get(i) == key:
            return db.session.get(VProblem, i)
    return None
