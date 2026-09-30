from flask import render_template, redirect, url_for, request, flash, jsonify, abort, current_app
from flask_login import current_user, login_required

from app import db
from app.user.models import User
from app.user.routes import admin_only, pw_check
from . import messages_bp
from . import services as M
from .models import Message, unread_for_student, unread_for_teachers


# ---------------------------------------------------------------- teachers

#route to the teacher's inbox: every student's conversation, unread first
@messages_bp.route('/messages', methods=['GET'])
@login_required
@pw_check
@admin_only
def inbox():
    return render_template('inbox.html', rows=M.inbox(), pinned=M.pinned_announcements(), title='Messages')

#route to one student's conversation, as a teacher
@messages_bp.route('/messages/<int:student_id>', methods=['GET'])
@login_required
@pw_check
@admin_only
def conversation(student_id):
    student = db.get_or_404(User, student_id)
    items = M.thread(student.id)
    M.mark_seen_by_teachers(student.id)
    return render_template('conversation.html', student=student, items=items, title='Messages: {}'.format(student.username))

#route for a teacher to send to one student, chosen students, or everyone
@messages_bp.route('/messages/send', methods=['POST'])
@login_required
@pw_check
@admin_only
def send():
    back = request.referrer or url_for('messages.inbox')
    to = request.form.get('to', '')
    if to == 'chosen':
        to = request.form.getlist('students')
        if not to:
            flash('Tick at least one student.', 'error')
            return redirect(back)
    try:
        students = M.send(current_user, to, request.form.get('body'), pinned=bool(request.form.get('pin')))
    except M.MessageError as exc:
        flash(str(exc), 'error')
        return redirect(back)
    pinned = ' and pinned to the top of their home page{}'.format('' if len(students) == 1 else 's') if request.form.get('pin') else ''
    if len(students) == 1 and to != 'all':
        flash('Message sent to {}{}.'.format(students[0].username, pinned), 'success')
        return redirect(url_for('messages.conversation', student_id=students[0].id))
    flash('Announcement sent to {} student{}{}.'.format(len(students), '' if len(students) == 1 else 's', pinned), 'success')
    current_app.logger.info('{} sent an announcement to {} students'.format(current_user.username, len(students)))
    return redirect(back)

#route to pin or unpin a message (and every copy sent with it)
@messages_bp.route('/messages/pin/<int:message_id>', methods=['POST'])
@login_required
@pw_check
@admin_only
def pin(message_id):
    msg = db.get_or_404(Message, message_id)
    pinned = request.form.get('pinned') == '1'
    count = M.set_pinned(msg, pinned)
    flash('{} for {} student{}.'.format('Pinned' if pinned else 'Unpinned', count, '' if count == 1 else 's'), 'success')
    return redirect(request.referrer or url_for('messages.inbox'))


# ---------------------------------------------------------------- students

#route for a student to reply to their teachers (shown on their home page)
@messages_bp.route('/messages/reply', methods=['POST'])
@login_required
@pw_check
def reply():
    if current_user.is_admin:
        abort(404)
    try:
        M.reply(current_user, request.form.get('body'))
        flash('Message sent to your teacher.', 'success')
    except M.MessageError as exc:
        flash(str(exc), 'error')
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
    """Pinned announcements and recent messages for a student's home page;
    opening it marks them seen."""
    items = M.thread(user.id, limit=30)
    pinned = M.pinned_for(user.id)
    unread_ids = {m.id for m in items + pinned if m.from_teacher and not m.seen_by_student}
    if mark_seen:
        M.mark_seen_by_student(user.id, items + pinned)
    return {'items': items, 'pinned': pinned, 'unread_ids': unread_ids, 'max_len': M.MAX_LEN}


# ---------------------------------------------------------------- both

#pages ask every 30 seconds whether anything new has arrived
@messages_bp.route('/messages/poll', methods=['GET'])
@login_required
def poll():
    if current_user.is_admin:
        return jsonify(unread=unread_for_teachers())
    latest = Message.query.filter_by(student_id=current_user.id).order_by(Message.id.desc()).first()
    return jsonify(unread=unread_for_student(current_user.id), latest=latest.id if latest else 0)
