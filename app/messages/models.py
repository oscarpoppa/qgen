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
    #the student removed this teacher's message from their own view (teachers still see it)
    hidden_for_student = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())
    #a student's message: to every teacher, or (False) only to those in MessageTo
    to_all = db.Column(db.Boolean, default=True, nullable=False, server_default=db.true())

    __table_args__ = (db.Index('ix_message_student_created', 'student_id', 'created'),)

    student = db.relationship('User', foreign_keys=[student_id])
    sender = db.relationship('User', foreign_keys=[sender_id])
    reads = db.relationship('MessageRead', cascade='all, delete-orphan', passive_deletes=True)
    to = db.relationship('MessageTo', cascade='all, delete-orphan', passive_deletes=True, lazy='selectin')

    @property
    def recipients(self):
        """The teachers a student's private message went to (empty: all of them)."""
        return [] if self.to_all else [t.teacher for t in self.to if t.teacher]


#the teacher(s) a student wrote to when not writing to all of them; only they see it
class MessageTo(db.Model):
    __tablename__ = 'message_to'
    message_id = db.Column(db.Integer, db.ForeignKey('message.id', ondelete='CASCADE'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True, index=True)

    teacher = db.relationship('User')


#each teacher's own record of a student's message or teacher notice: a row means that
#teacher has seen it, and cleared=True that they removed the notice from their own
#Notices panel. So every teacher gets every alert, whatever the others have read.
#(seen_by_teacher above still says whether any teacher has seen it.)
class MessageRead(db.Model):
    __tablename__ = 'message_read'
    message_id = db.Column(db.Integer, db.ForeignKey('message.id', ondelete='CASCADE'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True, index=True)
    cleared = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())


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
#what a student sees of their own record
VISIBLE_TO_STUDENT = Message.hidden_for_student.is_(False)


def unread_for_student(user_id):
    """Unread conversation messages (and announcements) for a student."""
    return Message.query.filter(Message.student_id == user_id, Message.from_teacher.is_(True),
                                Message.seen_by_student.is_(False), NOT_NOTICE, VISIBLE_TO_STUDENT).count()


def unread_notices_for_student(user_id):
    return Message.query.filter(Message.student_id == user_id, Message.from_teacher.is_(True),
                                Message.seen_by_student.is_(False), IS_NOTICE).count()


def for_teacher(teacher_id):
    """Condition: this teacher may see the message: anything from a teacher (and notices),
    a student's message to all teachers, or one sent to this teacher."""
    return db.or_(Message.from_teacher.is_(True), Message.to_all.is_(True),
                  db.exists().where(MessageTo.message_id == Message.id, MessageTo.user_id == teacher_id))


def seen_by(teacher_id):
    """Condition: this teacher has seen the message (or notice)."""
    return db.exists().where(MessageRead.message_id == Message.id, MessageRead.user_id == teacher_id)


def cleared_by(teacher_id):
    """Condition: this teacher has cleared the notice from their Notices panel."""
    return db.exists().where(MessageRead.message_id == Message.id, MessageRead.user_id == teacher_id,
                             MessageRead.cleared.is_(True))


def unread_for_teachers(teacher_id):
    """Messages from students this teacher hasn't seen."""
    return Message.query.filter(Message.from_teacher.is_(False), NOT_NOTICE, ~seen_by(teacher_id),
                                for_teacher(teacher_id)).count()


def unread_notices_for_teachers(teacher_id):
    return Message.query.filter(Message.from_teacher.is_(False), IS_NOTICE, ~seen_by(teacher_id)).count()
