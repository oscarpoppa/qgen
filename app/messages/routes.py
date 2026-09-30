from flask import render_template, redirect, url_for, request, flash, jsonify, abort, current_app
from flask_login import current_user, login_required

from app import db
from app.user.models import User
from app.jsoncsrf import post_form_only
from app.user.routes import admin_only, pw_check
from . import messages_bp
from . import services as M
from .models import (Message, NOT_NOTICE, IS_NOTICE, unread_for_student, unread_for_teachers,
                     unread_notices_for_student, unread_notices_for_teachers)


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
    items = M.conversation(student.id)
    M.mark_seen_by_teachers(student.id)
    return render_template('conversation.html', student=student, items=items, rows=M.inbox(),
                           title='Messages: {}'.format(student.username))

#route for a teacher to send to one student, chosen students, or everyone
@messages_bp.route('/messages/send', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def send():
    back = request.referrer or url_for('messages.inbox')
    to = request.form.get('to', '')
    if wants_json():
        #from the side panel: stays on the page it's on
        try:
            M.send(current_user, to, request.form.get('body'))
        except M.MessageError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True)
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
    if not request.form.get('pin'):
        pinned = ''
    elif len(students) == 1:
        pinned = ' and pinned to the top of {}\'s home page'.format(students[0].username)
    else:
        pinned = ' and pinned to the top of their home pages'
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
@post_form_only
def pin(message_id):
    msg = db.get_or_404(Message, message_id)
    pinned = request.form.get('pinned') == '1'
    count = M.set_pinned(msg, pinned)
    flash('{} for {} student{}.'.format('Pinned' if pinned else 'Unpinned', count, '' if count == 1 else 's'), 'success')
    return redirect(request.referrer or url_for('messages.inbox'))


# ---------------------------------------------------------------- students

#route for a student to reply to the teachers (shown on the student's home page)
@messages_bp.route('/messages/reply', methods=['POST'])
@login_required
@pw_check
@post_form_only
def reply():
    if current_user.is_admin:
        abort(404)
    if wants_json():
        try:
            M.reply(current_user, request.form.get('body'))
        except M.MessageError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True)
    try:
        M.reply(current_user, request.form.get('body'))
        flash('Message sent to your teacher.', 'success')
    except M.MessageError as exc:
        flash(str(exc), 'error')
    return redirect(request.referrer or url_for('user.mypage'))

def wants_json():
    """Sent by the side panel's script (which reloads the panel itself), not a plain form."""
    return request.headers.get('X-Requested-With') == 'fetch'


#the messages side panel (every page), reloaded by the page when something new arrives
@messages_bp.route('/messages/panel', methods=['GET'])
@login_required
@pw_check
def panel():
    if current_user.is_admin:
        return render_template('_teacher_messages.html', **teacher_panel(request.args.get('student', type=int)))
    return render_template('_student_messages.html', **student_panel(current_user))

#the notices side panel: automatic notices, apart from the conversation; showing them marks them seen
@messages_bp.route('/messages/notices', methods=['GET'])
@login_required
@pw_check
def notices():
    if current_user.is_admin:
        items = M.notices_for_teachers()
        unread_ids = {m.id for m in items if not m.seen_by_teacher}
        M.mark_notices_seen_by_teachers()
    else:
        items = M.notices_for_student(current_user.id)
        unread_ids = {m.id for m in items if not m.seen_by_student}
        M.mark_seen_by_student(current_user.id, items)
    return render_template('_notices.html', items=items, unread_ids=unread_ids, teacher=current_user.is_admin)


def student_panel(user, mark_seen=True):
    """Pinned announcements and recent messages for a student's home page;
    opening it marks them seen."""
    items = M.conversation(user.id, limit=30)
    pinned = M.pinned_for(user.id)
    unread_ids = {m.id for m in items + pinned if m.from_teacher and not m.seen_by_student}
    if mark_seen:
        M.mark_seen_by_student(user.id, items + pinned)
    return {'items': items, 'pinned': pinned, 'unread_ids': unread_ids, 'max_len': M.MAX_LEN}


def teacher_panel(student_id=None, mark_seen=True):
    """The messages box on a teacher's home page: one conversation at a time, with a
    menu of every student (unread first). Without a choice it opens the conversation
    that most needs attention. Showing a conversation marks it seen."""
    rows = M.inbox()
    chosen = next((r for r in rows if r['student'].id == student_id), None) if student_id else None
    if chosen is None:
        chosen = next((r for r in rows if r['unread']), None) or next((r for r in rows if r['last']), None) \
            or (rows[0] if rows else None)
    student = chosen['student'] if chosen else None
    items = M.conversation(student.id, limit=30) if student else []
    unread_ids = {m.id for m in items if not m.from_teacher and not m.seen_by_teacher}
    if student and mark_seen:
        M.mark_seen_by_teachers(student.id)
        chosen['unread'] = 0
    return {'rows': rows, 'student': student, 'items': items, 'unread_ids': unread_ids,
            'others_unread': sum(r['unread'] for r in rows), 'max_len': M.MAX_LEN}


# ---------------------------------------------------------------- both

#pages ask every 30 seconds whether anything new has arrived: unread counts for the two
#side panels' buttons, the newest ids (a panel reloads when they change), and a short
#preview of the newest unread item for the pop-up shown while a panel is hidden
@messages_bp.route('/messages/poll', methods=['GET'])
@login_required
def poll():
    if current_user.is_admin:
        mine = Message.query.filter(Message.from_teacher.is_(False))
        unseen = Message.seen_by_teacher.is_(False)
        unread, notices = unread_for_teachers(), unread_notices_for_teachers()
    else:
        mine = Message.query.filter(Message.student_id == current_user.id, Message.from_teacher.is_(True))
        unseen = Message.seen_by_student.is_(False)
        unread, notices = unread_for_student(current_user.id), unread_notices_for_student(current_user.id)
    newest = lambda q: q.order_by(Message.id.desc()).first()
    latest, latest_notice = newest(mine.filter(NOT_NOTICE)), newest(mine.filter(IS_NOTICE))
    new_msg, new_notice = newest(mine.filter(NOT_NOTICE, unseen)), newest(mine.filter(IS_NOTICE, unseen))
    return jsonify(unread=unread, notices=notices,
                   latest=latest.id if latest else 0, latest_notice=latest_notice.id if latest_notice else 0,
                   message_preview=preview(new_msg), notice_preview=preview(new_notice))


def preview(m):
    """Who and the first words, for the pop-up (the page shows it as plain text)."""
    if not m:
        return None
    who = (m.sender.username if m.sender else 'Teacher') if m.from_teacher else m.student.username
    body = m.body if len(m.body) <= 90 else m.body[:87].rstrip() + '…'
    return {'id': m.id, 'from': None if m.kind == 'notice' else who, 'text': body}
