from datetime import datetime

from app import db


#one conversation per student, shared by all teachers; also carries
#announcements (to everyone) and automatic notices. Notices are kept out of the
#conversation and shown in their own panel: from_teacher=True notices are for the
#student (quiz assigned, graded, ...), from_teacher=False ones are for teachers
#about that student (handed in, waiting for grading, signed up).
class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    from_teacher = db.Column(db.Boolean, default=True, nullable=False)
    #'message', 'announcement' or 'notice'
    kind = db.Column(db.String(16), default='message', nullable=False)
    body = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(256))
    created = db.Column(db.DateTime, default=datetime.now, nullable=False)
    seen_by_student = db.Column(db.Boolean, default=False, nullable=False)
    seen_by_teacher = db.Column(db.Boolean, default=False, nullable=False)
    #an announcement kept at the top of students' home pages
    pinned = db.Column(db.Boolean, default=False, nullable=False)
    #rows sent together (one broadcast) share this, so they're pinned or unpinned together
    batch = db.Column(db.String(32), index=True)

    __table_args__ = (db.Index('ix_message_student_created', 'student_id', 'created'),)

    student = db.relationship('User', foreign_keys=[student_id])
    sender = db.relationship('User', foreign_keys=[sender_id])


def notify(student_id, body, link=None, kind='notice', sender_id=None):
    """Add an automatic notice to a student's messages (committed by the caller)."""
    msg = Message(student_id=student_id, body=body, link=link, kind=kind, sender_id=sender_id,
                  from_teacher=True, seen_by_teacher=True)
    db.session.add(msg)
    return msg


def notify_teachers(student_id, body, link=None):
    """An automatic notice for teachers about a student (committed by the caller)."""
    msg = Message(student_id=student_id, body=body, link=link, kind='notice',
                  from_teacher=False, seen_by_student=True)
    db.session.add(msg)
    return msg


NOT_NOTICE = Message.kind != 'notice'
IS_NOTICE = Message.kind == 'notice'


def unread_for_student(user_id):
    """Unread conversation messages (and announcements) for a student."""
    return Message.query.filter(Message.student_id == user_id, Message.from_teacher.is_(True),
                                Message.seen_by_student.is_(False), NOT_NOTICE).count()


def unread_notices_for_student(user_id):
    return Message.query.filter(Message.student_id == user_id, Message.from_teacher.is_(True),
                                Message.seen_by_student.is_(False), IS_NOTICE).count()


def unread_for_teachers():
    """Unread messages from students."""
    return Message.query.filter(Message.from_teacher.is_(False), Message.seen_by_teacher.is_(False), NOT_NOTICE).count()


def unread_notices_for_teachers():
    return Message.query.filter(Message.from_teacher.is_(False), Message.seen_by_teacher.is_(False), IS_NOTICE).count()
