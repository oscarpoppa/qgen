from datetime import datetime

from flask import render_template, redirect, url_for, request, flash, jsonify, abort, current_app
from flask_login import current_user, login_required

from app import db
from app.jsoncsrf import json_csrf_ok
from app.user.models import User
from app.user.routes import admin_only, pw_check
from . import messages_bp
from .models import Message, unread_for_student, unread_for_teachers

MAX_LEN = 2000


def clean_body(text):
    text = (text or '').strip()
    if not text:
        return None, 'Please write a message first.'
    if len(text) > MAX_LEN:
        return None, 'Please keep messages under {} characters.'.format(MAX_LEN)
    return text, None


def thread(student_id, limit=None):
    q = Message.query.filter_by(student_id=student_id).order_by(Message.created.desc(), Message.id.desc())
    items = q.limit(limit).all() if limit else q.all()
    return list(reversed(items))


# ---------------------------------------------------------------- teachers

#route to the teacher's inbox: every student's conversation, unread first
@messages_bp.route('/messages', methods=['GET'])
@login_required
@pw_check
@admin_only
def inbox():
    students = User.query.filter_by(is_admin=False).order_by(User.username).all()
    rows = []
    for s in students:
        last = Message.query.filter_by(student_id=s.id).order_by(Message.created.desc(), Message.id.desc()).first()
        unread = Message.query.filter_by(student_id=s.id, from_teacher=False, seen_by_teacher=False).count()
        rows.append({'student': s, 'last': last, 'unread': unread})
    rows.sort(key=lambda r: (-r['unread'], -(r['last'].created.timestamp() if r['last'] else 0), r['student'].username))
    return render_template('inbox.html', rows=rows, title='Messages')

#route to one student's conversation, as a teacher
@messages_bp.route('/messages/<int:student_id>', methods=['GET'])
@login_required
@pw_check
@admin_only
def conversation(student_id):
    student = db.get_or_404(User, student_id)
    items = thread(student.id)
    Message.query.filter_by(student_id=student.id, from_teacher=False, seen_by_teacher=False).update({'seen_by_teacher': True})
    db.session.commit()
    return render_template('conversation.html', student=student, items=items, title='Messages: {}'.format(student.username))

#route for a teacher to send to one student, or an announcement to every student
@messages_bp.route('/messages/send', methods=['POST'])
@login_required
@pw_check
@admin_only
def send():
    body, err = clean_body(request.form.get('body'))
    to = request.form.get('to', '')
    back = request.referrer or url_for('messages.inbox')
    if err:
        flash(err, 'error')
        return redirect(back)
    if to == 'all':
        students = User.query.filter_by(is_admin=False).all()
        for s in students:
            db.session.add(Message(student_id=s.id, sender_id=current_user.id, from_teacher=True,
                                   kind='announcement', body=body, seen_by_teacher=True))
        db.session.commit()
        flash('Announcement sent to {} student{}.'.format(len(students), '' if len(students) == 1 else 's'), 'success')
        current_app.logger.info('{} sent an announcement to all students'.format(current_user.username))
        return redirect(back)
    student = db.session.get(User, int(to)) if to.isdigit() else None
    if not student or student.is_admin:
        flash('Please choose a student.', 'error')
        return redirect(back)
    db.session.add(Message(student_id=student.id, sender_id=current_user.id, from_teacher=True,
                           body=body, seen_by_teacher=True))
    db.session.commit()
    flash('Message sent to {}.'.format(student.username), 'success')
    return redirect(url_for('messages.conversation', student_id=student.id))


# ---------------------------------------------------------------- students

#route for a student to reply to their teachers (shown on their home page)
@messages_bp.route('/messages/reply', methods=['POST'])
@login_required
@pw_check
def reply():
    if current_user.is_admin:
        abort(404)
    body, err = clean_body(request.form.get('body'))
    if err:
        flash(err, 'error')
    else:
        db.session.add(Message(student_id=current_user.id, sender_id=current_user.id, from_teacher=False,
                               body=body, seen_by_student=True))
        db.session.commit()
        flash('Message sent to your teacher.', 'success')
    return redirect(url_for('user.mypage') + '#messages')

#the messages box on the student home page, reloaded by the page when something new arrives
@messages_bp.route('/messages/panel', methods=['GET'])
@login_required
@pw_check
def panel():
    if current_user.is_admin:
        abort(404)
    return render_template('_student_messages.html', **student_panel(current_user))


def student_panel(user, mark_seen=True):
    """Recent messages for a student's home page; opening it marks them seen."""
    items = thread(user.id, limit=30)
    unread_ids = {m.id for m in items if m.from_teacher and not m.seen_by_student}
    if mark_seen and unread_ids:
        Message.query.filter(Message.id.in_(unread_ids)).update({'seen_by_student': True}, synchronize_session=False)
        db.session.commit()
    return {'items': items, 'unread_ids': unread_ids, 'max_len': MAX_LEN}


# ---------------------------------------------------------------- both

#pages ask every 30 seconds whether anything new has arrived
@messages_bp.route('/messages/poll', methods=['GET'])
@login_required
def poll():
    if current_user.is_admin:
        return jsonify(unread=unread_for_teachers())
    latest = Message.query.filter_by(student_id=current_user.id).order_by(Message.id.desc()).first()
    return jsonify(unread=unread_for_student(current_user.id), latest=latest.id if latest else 0)
