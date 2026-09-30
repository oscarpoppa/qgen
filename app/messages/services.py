"""Sending and reading messages, shared by the web pages and the REST API."""
import uuid
from datetime import datetime

from app import db
from app.user.models import User
from .models import Message

MAX_LEN = 2000


class MessageError(ValueError):
    """Can't send, worded for people."""


def clean_body(text):
    text = (text or '').strip()
    if not text:
        raise MessageError('Please write a message first.')
    if len(text) > MAX_LEN:
        raise MessageError('Please keep messages under {} characters.'.format(MAX_LEN))
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
    """From a student to their teachers."""
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


def thread(student_id, limit=None):
    q = Message.query.filter_by(student_id=student_id).order_by(Message.created.desc(), Message.id.desc())
    items = q.limit(limit).all() if limit else q.all()
    return list(reversed(items))


def pinned_for(student_id):
    return Message.query.filter_by(student_id=student_id, pinned=True).order_by(Message.created.desc()).all()


def mark_seen_by_student(student_id, messages):
    ids = [m.id for m in messages if m.from_teacher and not m.seen_by_student]
    if ids:
        Message.query.filter(Message.id.in_(ids)).update({'seen_by_student': True}, synchronize_session=False)
        db.session.commit()
    return set(ids)


def mark_seen_by_teachers(student_id):
    Message.query.filter_by(student_id=student_id, from_teacher=False, seen_by_teacher=False).update({'seen_by_teacher': True})
    db.session.commit()


def inbox():
    """Every student's conversation for teachers: unread first, then most recent."""
    rows = []
    for s in User.query.filter_by(is_admin=False).order_by(User.username).all():
        last = Message.query.filter_by(student_id=s.id).order_by(Message.created.desc(), Message.id.desc()).first()
        unread = Message.query.filter_by(student_id=s.id, from_teacher=False, seen_by_teacher=False).count()
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
