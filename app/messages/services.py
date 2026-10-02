"""Sending and reading messages, shared by the web pages and the REST API."""
import uuid
from datetime import datetime

from app import db
from app.user.models import User
from sqlalchemy.exc import IntegrityError

from .models import Message, MessageRead, NOT_NOTICE, IS_NOTICE, VISIBLE_TO_STUDENT, seen_by, cleared_by

def max_len():
    """The longest a message can be (Technical settings)."""
    from app import tuning
    return tuning.get('max_message')


class MessageError(ValueError):
    """Can't send, worded for people."""


def clean_body(text):
    text = (text or '').strip()
    if not text:
        raise MessageError('Please write a message first.')
    if len(text) > max_len():
        raise MessageError('Please keep messages under {:,} characters.'.format(max_len()))
    return text


def students_for(to):
    """'all', a student id, or a list of ids -> the students (teachers can't be recipients)."""
    if to == 'all':
        return User.query.filter_by(is_admin=False).order_by(User.username).all()
    ids = to if isinstance(to, (list, tuple, set)) else [to]
    try:
        ids = {int(i) for i in ids}
    except (TypeError, ValueError):
        raise MessageError('Please choose students.')
    students = User.query.filter(User.id.in_(ids), User.is_admin.is_(False)).all() if ids else []
    if not students or len(students) != len(ids):
        raise MessageError('Please choose students (teachers can\'t be sent student messages).')
    return students


def send(sender, to, body, pinned=False):
    """From a teacher to one student, chosen students, or 'all'. One message per student;
    several at once form an announcement that can be pinned and unpinned together.
    Returns the students it went to."""
    body = clean_body(body)
    students = students_for(to)
    group = to == 'all' or len(students) > 1
    batch = uuid.uuid4().hex if group or pinned else None
    for s in students:
        db.session.add(Message(student_id=s.id, sender_id=sender.id, from_teacher=True,
                               kind='announcement' if group else 'message', body=body,
                               seen_by_teacher=True, pinned=bool(pinned), batch=batch))
    db.session.commit()
    return students


def reply(student, body):
    """From a student to the teachers."""
    if student.is_admin:
        raise MessageError('Teachers write from Messages.')
    db.session.add(Message(student_id=student.id, sender_id=student.id, from_teacher=False,
                           body=clean_body(body), seen_by_student=True))
    db.session.commit()


def set_pinned(message, pinned):
    """Pin or unpin a message, and every copy sent with it."""
    rows = Message.query.filter_by(batch=message.batch).all() if message.batch else [message]
    for m in rows:
        m.pinned = bool(pinned)
    db.session.commit()
    return len(rows)


def _newest(q, limit, unread=None):
    """The newest `limit` rows, newest first, plus every older one still unread (the
    condition `unread`), so nothing waiting to be read is ever left out of a panel,
    however long someone was away."""
    order = (Message.created.desc(), Message.id.desc())
    if not limit:
        return q.order_by(*order).all()
    items = q.order_by(*order).limit(limit).all()
    if unread is not None and len(items) == limit:
        older = q.filter(unread, Message.id.notin_([m.id for m in items])).order_by(*order).all()
        items = sorted(items + older, key=lambda m: (m.created, m.id), reverse=True)
    return items


def _oldest_first(q, limit, unread=None):
    return list(reversed(_newest(q, limit, unread)))


def unread_by_student():
    """For a student's panels: what a teacher sent that the student hasn't seen."""
    return db.and_(Message.from_teacher.is_(True), Message.seen_by_student.is_(False))


def unread_by_teacher(teacher):
    """For a teacher's panels: what students sent (or notices) this teacher hasn't seen."""
    return db.and_(Message.from_teacher.is_(False), ~seen_by(teacher.id))


def thread(student_id, limit=None):
    """Everything in a student's record the student may see: the conversation,
    announcements and the student's own notices (not teachers' notices about the student)."""
    q = Message.query.filter(Message.student_id == student_id,
                             db.or_(NOT_NOTICE, Message.from_teacher.is_(True)), VISIBLE_TO_STUDENT)
    return _oldest_first(q, limit)


def conversation(student_id, limit=None, for_student=False, unread=None):
    """Just what people wrote (messages and announcements), oldest first. for_student
    leaves out teachers' messages the student removed from their view, and pinned
    ones: the student sees those once, in the pinned box at the top. With a limit,
    anything unread (the condition `unread`) is included even if older."""
    q = Message.query.filter(Message.student_id == student_id, NOT_NOTICE)
    if for_student:
        q = q.filter(VISIBLE_TO_STUDENT, Message.pinned.is_(False))
    return _oldest_first(q, limit, unread)


def everyone(limit=60, unread=None):
    """The newest messages from all conversations together (no notices), oldest first.
    An announcement sent to several students appears once (its first copy), with
    `.copies` saying how many students got it."""
    items = _oldest_first(Message.query.filter(NOT_NOTICE), limit * 4, unread)
    out, seen = [], set()
    for m in items:
        if m.batch and m.kind == 'announcement':
            if m.batch in seen:
                continue
            seen.add(m.batch)
            m.copies = Message.query.filter_by(batch=m.batch).count()
        else:
            m.copies = 1
        out.append(m)
    #the newest `limit`, and anything older still unread
    newest = {m.id for m in out[-limit:]}
    unread_ids = set() if unread is None else \
        {r[0] for r in Message.query.filter(NOT_NOTICE, unread).with_entities(Message.id)}
    return [m for m in out if m.id in newest or m.id in unread_ids]


def _mark_for_teacher(teacher, ids, cleared=False):
    """Record that this teacher has seen (or cleared) these messages. Also sets
    seen_by_teacher, which says whether any teacher has seen them."""
    ids = set(ids)
    if not ids:
        return
    for attempt in (1, 2):
        have = {r.message_id: r for r in MessageRead.query.filter(MessageRead.user_id == teacher.id,
                                                                  MessageRead.message_id.in_(ids))}
        for i in ids:
            if i not in have:
                db.session.add(MessageRead(message_id=i, user_id=teacher.id, cleared=cleared))
            elif cleared:
                have[i].cleared = True
        Message.query.filter(Message.id.in_(ids), Message.seen_by_teacher.is_(False)) \
            .update({'seen_by_teacher': True}, synchronize_session=False)
        try:
            db.session.commit()
            return
        except IntegrityError:
            #the same teacher's other tab got there first; look again
            db.session.rollback()
            if attempt == 2:
                raise


def unseen_ids(teacher, messages):
    """Which of these students' messages and notices this teacher hasn't seen yet."""
    ids = [m.id for m in messages if not m.from_teacher]
    if not ids:
        return set()
    seen = {r.message_id for r in MessageRead.query.filter(MessageRead.user_id == teacher.id,
                                                           MessageRead.message_id.in_(ids))}
    return set(ids) - seen


def mark_messages_seen_by_teachers(teacher, messages):
    """Mark these students' messages read for this teacher (those just shown to them)."""
    _mark_for_teacher(teacher, [m.id for m in messages if not m.from_teacher and m.kind != 'notice'])


def notices_for_student(student_id, limit=30):
    """A student's automatic notices, newest first (and every unread one)."""
    return _newest(Message.query.filter(Message.student_id == student_id, IS_NOTICE, Message.from_teacher.is_(True)),
                   limit, unread_by_student())


def notices_for_teachers(teacher, limit=50):
    """Automatic notices for teachers (about all students), newest first (and every one
    this teacher hasn't seen), less the ones this teacher has cleared."""
    return _newest(Message.query.filter(IS_NOTICE, Message.from_teacher.is_(False), ~cleared_by(teacher.id)),
                   limit, unread_by_teacher(teacher))


def mark_notices_seen_by_teachers(teacher):
    """This teacher has seen all their notices (the other teachers' alerts stay)."""
    ids = [r[0] for r in Message.query.filter(IS_NOTICE, Message.from_teacher.is_(False), ~seen_by(teacher.id))
           .with_entities(Message.id)]
    _mark_for_teacher(teacher, ids)


def pinned_for(student_id):
    """A student's pinned messages: shown until the teacher unpins them (a student can't
    remove a pinned message, so these show even if removed before this rule)."""
    return Message.query.filter(Message.student_id == student_id, Message.pinned.is_(True), NOT_NOTICE) \
        .order_by(Message.created.desc()).all()


def mark_seen_by_student(student_id, messages):
    ids = [m.id for m in messages if m.from_teacher and not m.seen_by_student]
    if ids:
        Message.query.filter(Message.id.in_(ids)).update({'seen_by_student': True}, synchronize_session=False)
        db.session.commit()
    return set(ids)


def mark_seen_by_teachers(teacher, student_id):
    """This teacher has read this student's messages (notices are marked in their own panel)."""
    ids = [r[0] for r in Message.query.filter(Message.student_id == student_id, Message.from_teacher.is_(False),
                                              NOT_NOTICE, ~seen_by(teacher.id)).with_entities(Message.id)]
    _mark_for_teacher(teacher, ids)


def unread_from(teacher, student_id):
    """Messages from this student the teacher hasn't seen."""
    return Message.query.filter(Message.student_id == student_id, Message.from_teacher.is_(False),
                                NOT_NOTICE, ~seen_by(teacher.id)).count()


def inbox(teacher):
    """Every student's conversation for teachers: unread first, then most recent."""
    rows = []
    for s in User.query.filter_by(is_admin=False).order_by(User.username).all():
        last = Message.query.filter(Message.student_id == s.id, NOT_NOTICE) \
            .order_by(Message.created.desc(), Message.id.desc()).first()
        unread = unread_from(teacher, s.id)
        rows.append({'student': s, 'last': last, 'unread': unread})
    rows.sort(key=lambda r: (-r['unread'], -(r['last'].created.timestamp() if r['last'] else 0), r['student'].username))
    return rows


def pinned_announcements():
    """One entry per pinned broadcast, for the teacher's list."""
    seen, out = set(), []
    for m in Message.query.filter_by(pinned=True).order_by(Message.created.desc()).all():
        key = m.batch or m.id
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


# ---------------------------------------------------------------- deleting

def can_delete(user, m):
    """Conversation messages (not notices): teachers may delete any; a student may
    delete anything in their own conversation (a teacher's message only from their view)."""
    if m.kind == 'notice':
        return False
    if user.is_admin:
        return True
    #a pinned message stays on the student's page until the teacher unpins it
    return m.student_id == user.id and not (m.from_teacher and m.pinned)


def delete_message(user, m, everyone=False):
    """Delete a message for good; a student deleting a teacher's message only removes
    it from the student's view. For an announcement sent to several students, a
    teacher's everyone=True removes every copy. Returns how many."""
    if not can_delete(user, m):
        if not user.is_admin and m.student_id == user.id and m.pinned:
            raise MessageError('A pinned message stays until your teacher unpins it.')
        raise MessageError('You can only delete messages in your own conversation.')
    if not user.is_admin and m.from_teacher:
        m.hidden_for_student = True
        db.session.commit()
        return 1
    rows = Message.query.filter_by(batch=m.batch).all() if (everyone and m.batch and user.is_admin) else [m]
    for row in rows:
        db.session.delete(row)
    db.session.commit()
    return len(rows)


def _my_notices(user):
    """The notices shown in this person's Notices panel."""
    if user.is_admin:
        return Message.query.filter(IS_NOTICE, Message.from_teacher.is_(False))
    return Message.query.filter(IS_NOTICE, Message.from_teacher.is_(True), Message.student_id == user.id)


def clear_notices(user, notice_id=None):
    """Remove one notice (or all of them) from this person's Notices panel. Each teacher
    clears their own copy; a notice is deleted once every teacher has cleared it.
    Returns how many were removed."""
    q = _my_notices(user)
    if user.is_admin:
        q = q.filter(~cleared_by(user.id))
    if notice_id is not None:
        q = q.filter(Message.id == notice_id)
    rows = q.all()
    if notice_id is not None and not rows:
        raise MessageError('That notice isn\'t in your notices.')
    if not user.is_admin:
        for row in rows:
            db.session.delete(row)
        db.session.commit()
        return len(rows)
    _mark_for_teacher(user, [r.id for r in rows], cleared=True)
    _delete_if_all_cleared([r.id for r in rows])
    return len(rows)


def _delete_if_all_cleared(ids):
    """Delete the notices every teacher has now cleared."""
    teachers = [t[0] for t in User.query.filter_by(is_admin=True).with_entities(User.id)]
    if not ids or not teachers:
        return
    done = [r[0] for r in db.session.query(MessageRead.message_id)
            .filter(MessageRead.message_id.in_(ids), MessageRead.cleared.is_(True), MessageRead.user_id.in_(teachers))
            .group_by(MessageRead.message_id).having(db.func.count() >= len(teachers))]
    if done:
        for m in Message.query.filter(Message.id.in_(done)):
            db.session.delete(m)
        db.session.commit()
