from datetime import datetime

from app import db


#one conversation per student, shared by all teachers; also carries
#announcements (to everyone) and automatic notices (quiz assigned, graded, ...)
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

    __table_args__ = (db.Index('ix_message_student_created', 'student_id', 'created'),)

    student = db.relationship('User', foreign_keys=[student_id])
    sender = db.relationship('User', foreign_keys=[sender_id])


def notify(student_id, body, link=None, kind='notice', sender_id=None):
    """Add an automatic notice to a student's messages (committed by the caller)."""
    msg = Message(student_id=student_id, body=body, link=link, kind=kind, sender_id=sender_id,
                  from_teacher=True, seen_by_teacher=True)
    db.session.add(msg)
    return msg


def unread_for_student(user_id):
    return Message.query.filter_by(student_id=user_id, from_teacher=True, seen_by_student=False).count()


def unread_for_teachers():
    return Message.query.filter_by(from_teacher=False, seen_by_teacher=False).count()
