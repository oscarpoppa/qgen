"""Sending and reading messages, shared by the web pages and the REST API."""
import uuid
from datetime import datetime

from app import db
from app.user.models import User
from sqlalchemy.exc import IntegrityError

from .models import (Message, MessageRead, MessageTo, NOT_NOTICE, IS_NOTICE, VISIBLE_TO_STUDENT, seen_by, cleared_by, for_teacher,
                     own_notices, unread_teacher_notices)

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


def teachers_for_student():
    """The teachers a student can write to: online ones first, then by name."""
    teachers = User.query.filter_by(is_admin=True).order_by(User.username).all()
    return sorted(teachers, key=lambda t: (not t.online, t.username.lower()))


def teacher_choice(value):
    """'all' (or nothing) -> None; a teacher's id -> that teacher. Anything else is refused."""
    if value in (None, '', 'all'):
        return None
    try:
        teacher = db.session.get(User, int(value))
    except (TypeError, ValueError):
        teacher = None
    if teacher is None or not teacher.is_admin:
        raise MessageError('Please choose one of your teachers.')
    return teacher


def teachers_chosen(values):
    """Who a student's message goes to: None for every teacher ('all', nothing given, or
    every teacher checked), else the chosen teachers. values: one value or a list of
    them ('all' or teachers' ids); an empty list means none was checked."""
    if values is None or isinstance(values, (str, int, User)):
        values = [values]
    values = [v for v in values if v not in (None, '')] if values else []
    if not values:
        raise MessageError('Check at least one teacher to send it to.')
    if 'all' in values:
        return None
    teachers = list({t.id: t for t in (v if isinstance(v, User) else teacher_choice(v) for v in values)}.values())
    everyone = {t.id for t in User.query.filter_by(is_admin=True)}
    return None if {t.id for t in teachers} >= everyone else teachers


def reply(student, body, to=None):
    """From a student to all the teachers, or to some of them (to: a teacher, teachers'
    ids, or 'all'/None for all), in which case only those teachers see it."""
    if student.is_admin:
        raise MessageError('Teachers write from Messages.')
    teachers = teachers_chosen('all' if to is None else to)
    body = clean_body(body)
    msg = Message(student_id=student.id, sender_id=student.id, from_teacher=False, body=body,
                  seen_by_student=True, to_all=teachers is None)
    for teacher in teachers or []:
        msg.to.append(MessageTo(user_id=teacher.id))
    db.session.add(msg)
    db.session.commit()
    return msg


def with_teacher(teacher):
    """Condition, for a student's view: the conversation with one teacher (what that
    teacher wrote, and what the student sent to all teachers or to that teacher)."""
    return db.or_(db.and_(Message.from_teacher.is_(True), Message.sender_id == teacher.id),
                  db.and_(Message.from_teacher.is_(False),
                          db.or_(Message.to_all.is_(True),
                                 db.exists().where(MessageTo.message_id == Message.id, MessageTo.user_id == teacher.id))))


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


def thread(student_id, limit=None, teacher=None):
    """Everything in a student's record the student may see: the conversation,
    announcements and the student's own notices (not teachers' notices about the student)."""
    q = Message.query.filter(Message.student_id == student_id,
                             db.or_(NOT_NOTICE, Message.from_teacher.is_(True)), VISIBLE_TO_STUDENT)
    if teacher is not None:  # a teacher reading it: only what they may see
        q = q.filter(for_teacher(teacher.id))
    return _oldest_first(q, limit)


def conversation(student_id, limit=None, for_student=False, unread=None, teacher=None, only=None):
    """Just what people wrote (messages and announcements), oldest first. for_student
    leaves out teachers' messages the student removed from their view, and pinned
    ones: the student sees those once, in the pinned box at the top. With a limit,
    anything unread (the condition `unread`) is included even if older. teacher: the
    teacher looking (only what they may see); only: a student's view of the
    conversation with that one teacher."""
    q = Message.query.filter(Message.student_id == student_id, NOT_NOTICE)
    if for_student:
        q = q.filter(VISIBLE_TO_STUDENT, Message.pinned.is_(False))
    if teacher is not None:
        q = q.filter(for_teacher(teacher.id))
    if only is not None:
        q = q.filter(with_teacher(only))
    return _oldest_first(q, limit, unread)


def everyone(limit=60, unread=None, teacher=None):
    """The newest messages from all conversations together (no notices), oldest first.
    An announcement sent to several students appears once (its first copy), with
    `.copies` saying how many students got it."""
    q = Message.query.filter(NOT_NOTICE)
    if teacher is not None:
        q = q.filter(for_teacher(teacher.id))
    items = _oldest_first(q, limit * 4, unread)
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
        {r[0] for r in q.filter(unread).with_entities(Message.id)}
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
        try:
            #(the update writes the new rows first, so it can be the one that finds another tab's)
            Message.query.filter(Message.id.in_(ids), Message.seen_by_teacher.is_(False)) \
                .update({'seen_by_teacher': True}, synchronize_session=False)
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


def _teacher_panel_notices(teacher):
    """What's in a teacher's Notices panel: notices about the students, less the ones this
    teacher has cleared, and notices about the teacher's own quizzes."""
    return Message.query.filter(db.or_(db.and_(IS_NOTICE, Message.from_teacher.is_(False), ~cleared_by(teacher.id)),
                                       own_notices(teacher.id)))


def notices_for_teachers(teacher, limit=50):
    """A teacher's notices, newest first (and every one this teacher hasn't seen)."""
    return _newest(_teacher_panel_notices(teacher), limit, unread_teacher_notices(teacher.id))


def teacher_unseen_notices(teacher, items):
    """Which of these notices this teacher hasn't seen (about students, or their own quizzes)."""
    own = {m.id for m in items if m.from_teacher and m.student_id == teacher.id and not m.seen_by_student}
    return unseen_ids(teacher, items) | own


def mark_notices_seen_by_teachers(teacher):
    """This teacher has seen all their notices (the other teachers' alerts stay)."""
    ids = [r[0] for r in Message.query.filter(IS_NOTICE, Message.from_teacher.is_(False), ~seen_by(teacher.id))
           .with_entities(Message.id)]
    _mark_for_teacher(teacher, ids)
    _mark_own_notices_seen(teacher.id)


def _mark_own_notices_seen(user_id, ids=None):
    q = Message.query.filter(own_notices(user_id), Message.seen_by_student.is_(False))
    if ids is not None:
        q = q.filter(Message.id.in_(ids))
    if q.update({'seen_by_student': True}, synchronize_session=False):
        db.session.commit()


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
                                              NOT_NOTICE, ~seen_by(teacher.id), for_teacher(teacher.id))
           .with_entities(Message.id)]
    _mark_for_teacher(teacher, ids)


def unread_from(teacher, student_id):
    """Messages from this student the teacher hasn't seen."""
    return Message.query.filter(Message.student_id == student_id, Message.from_teacher.is_(False),
                                NOT_NOTICE, ~seen_by(teacher.id), for_teacher(teacher.id)).count()


def inbox(teacher):
    """Every student's conversation for teachers: unread first, then most recent."""
    rows = []
    for s in User.query.filter_by(is_admin=False).order_by(User.username).all():
        last = Message.query.filter(Message.student_id == s.id, NOT_NOTICE, for_teacher(teacher.id)) \
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
        #a student's message to another teacher isn't theirs to see, or delete
        return m.from_teacher or m.to_all or any(t.user_id == user.id for t in m.to)
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
        return _teacher_panel_notices(user)
    return Message.query.filter(IS_NOTICE, Message.from_teacher.is_(True), Message.student_id == user.id)


def clear_notices(user, notice_id=None):
    """Remove one notice (or all of them) from this person's Notices panel. Each teacher
    clears their own copy; a notice is deleted once every teacher has cleared it.
    Returns how many were removed."""
    q = _my_notices(user)
    if notice_id is not None:
        q = q.filter(Message.id == notice_id)
    rows = q.all()
    if notice_id is not None and not rows:
        raise MessageError('That notice isn\'t in your notices.')
    #your own notices (a student's, or a teacher's about quizzes they take) are deleted
    own = [r for r in rows if r.from_teacher]
    for row in own:
        db.session.delete(row)
    db.session.commit()
    shared = [r.id for r in rows if not r.from_teacher]
    if shared:
        _mark_for_teacher(user, shared, cleared=True)
        _delete_if_all_cleared(shared)
    return len(rows)


def mark_notice_seen(user, notice_id):
    """This person has seen one notice in their own Notices panel (clicked it)."""
    m = _my_notices(user).filter(Message.id == notice_id).first()
    if m is None:
        raise MessageError('That notice isn\'t in your notices.')
    if user.is_admin and not m.from_teacher:
        _mark_for_teacher(user, [m.id])
    else:
        mark_seen_by_student(user.id, [m])


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


# ---------------------------------------------------------------- between teachers

def other_teachers(me):
    """Every other teacher, online first, then by name."""
    teachers = User.query.filter(User.is_admin.is_(True), User.id != me.id).order_by(User.username).all()
    return sorted(teachers, key=lambda t: (not t.online, t.username.lower()))


def staff_choice(me, value):
    """'teachers' (or nothing) -> None, meaning all the teachers; 't<id>' or an id -> that
    other teacher. Anything else (a student, yourself, nonsense) is refused."""
    if value in (None, '', 'teachers', 'all'):
        return None
    try:
        teacher = db.session.get(User, int(str(value).lstrip('t')))
    except (TypeError, ValueError):
        teacher = None
    if teacher is None or not teacher.is_admin or teacher.id == me.id:
        raise MessageError('Please choose one of the other teachers.')
    return teacher


def send_to_teachers(me, body, to):
    """From one teacher to other teachers. to: 'all', or the chosen teachers' ids (a list;
    empty means none was checked). Every other teacher chosen is the same as 'all'."""
    from .models import StaffMessage, StaffMessageTo, StaffMessageRead
    if not me.is_admin:
        raise MessageError('Only teachers can write to teachers.')
    values = [to] if isinstance(to, (str, int)) else list(to or [])
    values = [v for v in values if v not in (None, '')]
    if not values:
        raise MessageError('Check at least one teacher to send it to.')
    others = {t.id for t in other_teachers(me)}
    if not others:
        raise MessageError('There are no other teachers yet.')
    if 'all' in values:
        chosen = None
    else:
        chosen = list({t.id: t for t in (staff_choice(me, v) for v in values)}.values())
        if {t.id for t in chosen} >= others:
            chosen = None
    msg = StaffMessage(sender_id=me.id, body=clean_body(body), to_all=chosen is None)
    for t in chosen or []:
        msg.to.append(StaffMessageTo(user_id=t.id))
    msg.reads.append(StaffMessageRead(user_id=me.id))  # your own is never "new"
    db.session.add(msg)
    db.session.commit()
    return msg


def teachers_thread(me, other=None, limit=50):
    """What this teacher can see of the teachers' messages, oldest first (the newest
    `limit`): everything (other None), or just between them and one other teacher (what
    either wrote to all teachers or to the other)."""
    from .models import StaffMessage, StaffMessageTo, staff_for
    q = StaffMessage.query.filter(staff_for(me.id))
    if other is not None:
        to_them = lambda uid: db.or_(StaffMessage.to_all.is_(True),
                                     db.exists().where(StaffMessageTo.message_id == StaffMessage.id, StaffMessageTo.user_id == uid))
        q = q.filter(db.or_(db.and_(StaffMessage.sender_id == me.id, to_them(other.id)),
                            db.and_(StaffMessage.sender_id == other.id, to_them(me.id))))
    rows = q.order_by(StaffMessage.created.desc(), StaffMessage.id.desc()).limit(limit).all()
    return rows[::-1]


def staff_unseen_ids(me, items):
    from .models import StaffMessageRead
    ids = [m.id for m in items]
    if not ids:
        return set()
    seen = {r.message_id for r in StaffMessageRead.query.filter(StaffMessageRead.user_id == me.id,
                                                                StaffMessageRead.message_id.in_(ids))}
    return set(ids) - seen


def mark_staff_seen(me, items):
    from .models import StaffMessageRead
    for mid in staff_unseen_ids(me, items):
        db.session.add(StaffMessageRead(message_id=mid, user_id=me.id))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()  # marked by another request at the same moment


def staff_unread_by_sender(me):
    """{other teacher's id: how many of their messages this teacher hasn't seen}."""
    from .models import StaffMessage, staff_for, staff_seen_by
    return dict(db.session.query(StaffMessage.sender_id, db.func.count(StaffMessage.id))
                .filter(staff_for(me.id), StaffMessage.sender_id.isnot(None), StaffMessage.sender_id != me.id,
                        ~staff_seen_by(me.id))
                .group_by(StaffMessage.sender_id).all())


def delete_staff_message(me, message_id):
    """A teacher removes a message they wrote (for everyone). True if removed."""
    from .models import StaffMessage
    msg = db.session.get(StaffMessage, message_id)
    if msg is None or msg.sender_id != me.id:
        return False
    db.session.delete(msg)
    db.session.commit()
    return True


def staff_state(me):
    """Changes whenever what this teacher can see of the teachers' messages changes."""
    from .models import StaffMessage, staff_for
    return ':'.join(str(v or 0) for v in StaffMessage.query.filter(staff_for(me.id)).with_entities(
        db.func.count(StaffMessage.id), db.func.max(StaffMessage.id), db.func.sum(StaffMessage.id)).one())
