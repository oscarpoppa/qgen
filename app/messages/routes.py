from flask import render_template, redirect, url_for, request, flash, jsonify, abort, current_app
from app.nav import back_to
from flask_login import current_user, login_required

from app import db, live
from app.user.models import User
from app.jsoncsrf import post_form_only
from app.user.routes import admin_only, pw_check
from app.home import home_url
from . import messages_bp
from . import services as M
from .models import (Message, NOT_NOTICE, IS_NOTICE, for_teacher, unread_for_student, unread_for_teachers,
                     unread_notices_for_student, unread_notices_for_teachers, seen_by, cleared_by,
                     unread_messages_for_teacher, own_notices, teacher_notices, unread_teacher_notices)
from app.qgen.models import new_quizzes


# ---------------------------------------------------------------- teachers

#route to the teacher's inbox: every student's conversation, unread first
@messages_bp.route('/messages', methods=['GET'])
@login_required
@pw_check
@admin_only
def inbox():
    from .models import unread_staff
    from app.user import groups
    rows = M.inbox(current_user)
    #the Users page's folders down the side: all students, those in no folder, or one folder
    #(with the folders inside it); each with how many unread messages are waiting in it
    root, flat, nodes, _ = groups.tree([r['student'] for r in rows])
    from app import folder_tree
    view, node = folder_tree.view_of(request.args.get('folder'), nodes, default='all')
    unread = {r['student'].id: r['unread'] for r in rows}
    for n in nodes.values():
        n['unread'] = sum(unread.get(i, 0) for i in n['everyone'])
    in_none = {u.id for u in root['people']}
    root['unread'] = sum(unread.get(i, 0) for i in in_none)
    shown = [r for r in rows if r['student'].id in node['everyone']] if node else \
        [r for r in rows if r['student'].id in in_none] if view == 'main' else rows
    path, up = [], node['folder'] if node else None
    while up is not None:
        path.insert(0, up)
        up = nodes[up.parent_id]['folder'] if up.parent_id in nodes else None
    return render_template('inbox.html', rows=rows, shown=shown, pinned=M.pinned_announcements(),
                           staff_unread=unread_staff(current_user.id), title='Messages', root=root, node=node, view=view,
                           path=path, user_folders=groups.picker(), students={r['student'].id for r in rows})

#route to one student's conversation, as a teacher
#how many of a conversation's messages its page shows at first (and adds with "Show older")
PAGE = 40


@messages_bp.route('/messages/<int:student_id>', methods=['GET'])
@login_required
@pw_check
@admin_only
def conversation(student_id):
    student = db.session.get(User, student_id)
    if student is None:
        flash("That student's account has been deleted.", 'info')
        return redirect(url_for('messages.inbox'))
    #the newest messages (a long conversation shows "Show older" for the rest), 40 at a time
    shown = max(request.args.get('show', type=int) or 0, PAGE)
    items = M.conversation(student.id, teacher=current_user, limit=shown + 1)
    older = len(items) > shown
    items = items[1:] if older else items
    M.mark_seen_by_teachers(current_user, student.id)
    return render_template('conversation.html', student=student, items=items, rows=M.inbox(current_user),
                           older=older, show_more=shown + PAGE,
                           title='Messages: {}'.format(student.shown_name))

#route for a teacher to send to one student, chosen students, or everyone
@messages_bp.route('/messages/send', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def send():
    back = back_to(url_for('messages.inbox'))
    to = request.form.get('to', '')
    if wants_json():
        #from the side panel: stays on the page it's on
        try:
            students = M.send(current_user, to, request.form.get('body'), pinned=bool(request.form.get('pin')))
        except M.MessageError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, sent=len(students))
    if to == 'chosen':
        to = request.form.getlist('students')
        if not to:
            flash('Check at least one student.', 'error')
            return redirect(back)
    elif to.startswith('folder:'):
        #everyone in a Users page folder (and the folders inside it) who is a student
        from app.user import groups
        try:
            ids = groups.everyone_in(to.split(':', 1)[1])
        except groups.GroupError as exc:
            flash(str(exc), 'error')
            return redirect(back)
        to = [u.id for u in User.query.filter(User.id.in_(ids), User.is_admin.is_(False))] if ids else []
        if not to:
            flash('Nobody in that folder is a student.', 'error')
            return redirect(back)
    try:
        students = M.send(current_user, to, request.form.get('body'), pinned=bool(request.form.get('pin')))
    except M.MessageError as exc:
        flash(str(exc), 'error')
        return redirect(back)
    if not request.form.get('pin'):
        pinned = ''
    elif len(students) == 1:
        pinned = ' and pinned to the top of {}\'s home page'.format(students[0].shown_name)
    else:
        pinned = ' and pinned to the top of their home pages'
    if len(students) == 1 and to != 'all':
        flash('Message sent to {}{}.'.format(students[0].shown_name, pinned), 'success')
        return redirect(url_for('messages.conversation', student_id=students[0].id))
    flash('Announcement sent to {} student{}{}.'.format(len(students), '' if len(students) == 1 else 's', pinned), 'success')
    current_app.logger.info('{} sent an announcement to {} students'.format(current_user.username, len(students)))
    return redirect(back)

#route for a teacher to write to other teachers (the checked ones, or all of them)
@messages_bp.route('/messages/teachers/send', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def send_staff():
    #a form with the checkboxes says so (to_checked): none checked isn't taken as "all"
    to = request.form.getlist('to') or ([] if request.form.get('to_checked') else 'all')
    try:
        msg = M.send_to_teachers(current_user, request.form.get('body'), to)
    except M.MessageError as exc:
        if wants_json():
            return jsonify(ok=False, error=str(exc)), 400
        flash(str(exc), 'error')
        return redirect(back_to(url_for('messages.teachers_page')))
    if wants_json():
        return jsonify(ok=True)
    flash('Message sent to {}.'.format(', '.join(t.shown_name for t in msg.recipients) if msg.recipients
                                       else 'all the teachers'), 'success')
    return redirect(back_to(url_for('messages.teachers_page')))

#route for a teacher to delete a message they wrote to teachers
@messages_bp.route('/messages/teachers/delete/<int:message_id>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def delete_staff(message_id):
    done = M.delete_staff_message(current_user, message_id)
    if wants_json():
        return (jsonify(ok=True), 200) if done else (jsonify(ok=False, error='You can only delete your own messages.'), 404)
    flash('Message deleted.' if done else 'You can only delete your own messages.', 'success' if done else 'error')
    return redirect(back_to(url_for('messages.teachers_page')))

#route to the messages between teachers as a page (all of them, or with one teacher)
@messages_bp.route('/messages/teachers', methods=['GET'])
@login_required
@pw_check
@admin_only
def teachers_page():
    choice = request.args.get('with') or 'teachers'
    view = teachers_view(M.inbox(current_user), staff_picker(current_user),
                         choice if choice == 'teachers' else 't' + choice.lstrip('t'))
    return render_template('teachers_messages.html', title='Messages between teachers', **view)

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
    if wants_json():
        return jsonify(ok=True)
    flash('{} for {} student{}.'.format('Pinned' if pinned else 'Unpinned', count, '' if count == 1 else 's'), 'success')
    return redirect(back_to(url_for('messages.inbox')))


#route to delete a message for good (teachers: any message; students: their own).
#An announcement sent to several students: everyone=1 removes every copy.
@messages_bp.route('/messages/delete/<int:message_id>', methods=['POST'])
@login_required
@pw_check
@post_form_only
def delete(message_id):
    msg = db.get_or_404(Message, message_id)
    everyone = request.form.get('everyone') == '1'
    try:
        count = M.delete_message(current_user, msg, everyone=everyone)
    except M.MessageError as exc:
        if wants_json():
            return jsonify(ok=False, error=str(exc)), 403
        flash(str(exc), 'error')
        return redirect(back_to(home_url()))
    current_app.logger.info('{} deleted {} message{}'.format(current_user.username, count, '' if count == 1 else 's'))
    if wants_json():
        return jsonify(ok=True, deleted=count)
    flash('Message deleted{}.'.format(' for all {} students who got it'.format(count) if count > 1 else ''), 'success')
    return redirect(back_to(home_url()))

#route to mark one notice seen (it was clicked in the Notices panel)
@messages_bp.route('/messages/notices/seen/<int:notice_id>', methods=['POST'])
@login_required
@pw_check
@post_form_only
def notice_seen(notice_id):
    try:
        M.mark_notice_seen(current_user, notice_id)
    except M.MessageError as exc:
        return jsonify(ok=False, error=str(exc)), 404
    return jsonify(ok=True)


#route to clear one notice (or, without an id, all of them) from your Notices panel
@messages_bp.route('/messages/notices/clear', methods=['POST'])
@messages_bp.route('/messages/notices/clear/<int:notice_id>', methods=['POST'])
@login_required
@pw_check
@post_form_only
def clear_notices(notice_id=None):
    try:
        count = M.clear_notices(current_user, notice_id)
    except M.MessageError as exc:
        if wants_json():
            return jsonify(ok=False, error=str(exc)), 404
        flash(str(exc), 'error')
        return redirect(back_to(home_url()))
    if wants_json():
        return jsonify(ok=True, cleared=count)
    return redirect(back_to(home_url()))


# ---------------------------------------------------------------- students

#route for a student to reply to the teachers (shown on the student's home page)
@messages_bp.route('/messages/reply', methods=['POST'])
@login_required
@pw_check
@post_form_only
def reply():
    if current_user.is_admin:
        abort(404)
    #to: 'all' (every teacher), or the checked teachers' ids (only they see it); a form
    #with the checkboxes says so (to_checked), so none checked isn't taken as "all"
    to = request.form.getlist('to') or (None if not request.form.get('to_checked') else [])
    if wants_json():
        try:
            M.reply(current_user, request.form.get('body'), to)
        except M.MessageError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True)
    try:
        msg = M.reply(current_user, request.form.get('body'), to)
        flash('Message sent to {}.'.format(', '.join(t.shown_name for t in msg.recipients) if msg.recipients else 'your teachers'), 'success')
    except M.MessageError as exc:
        flash(str(exc), 'error')
    return redirect(back_to(url_for('user.mypage')))

def wants_json():
    """Sent by the side panel's script (which reloads the panel itself), not a plain form."""
    return request.headers.get('X-Requested-With') == 'fetch'


#the messages side panel (every page), reloaded by the page when something new arrives
@messages_bp.route('/messages/panel', methods=['GET'])
@login_required
@pw_check
def panel():
    if current_user.is_admin:
        return render_template('_teacher_messages.html', **teacher_panel(request.args.get('student', 'all')))
    return render_template('_student_messages.html', **student_panel(current_user, request.args.get('student')))

#the notices side panel: automatic notices, apart from the conversation. Showing them
#doesn't mark them seen (an open panel reloads by itself as notices arrive); seen=1 does,
#sent when the person opens the panel with its button. A single notice is marked when
#it's clicked (notice_seen below), so a new one stays gold and counted until then.
@messages_bp.route('/messages/notices', methods=['GET'])
@login_required
@pw_check
def notices():
    mark = request.args.get('seen') == '1'
    if current_user.is_admin:
        items = M.notices_for_teachers(current_user)
        unread_ids = M.teacher_unseen_notices(current_user, items)
        if mark:
            M.mark_notices_seen_by_teachers(current_user)
    else:
        items = M.notices_for_student(current_user.id)
        unread_ids = {m.id for m in items if not m.seen_by_student}
        if mark:
            M.mark_seen_by_student(current_user.id, items)
    return render_template('_notices.html', items=items, unread_ids=unread_ids, teacher=current_user.is_admin)


def student_panel(user, choice=None, mark_seen=True):
    """A student's messages panel: pinned announcements, then the conversation with all
    the teachers (choice 'all', the default) or with one teacher (their id), and a box
    to write to them. Opening it marks what it shows as seen."""
    try:
        teacher = M.teacher_choice(choice)
    except M.MessageError:
        teacher = None  # e.g. a choice remembered from someone else in this browser
    items = M.conversation(user.id, limit=30, for_student=True, unread=M.unread_by_student(), only=teacher)
    pinned = M.pinned_for(user.id)
    unread_ids = {m.id for m in items + pinned if m.from_teacher and not m.seen_by_student}
    if mark_seen:
        M.mark_seen_by_student(user.id, items + pinned)
    #each teacher, online first, with how many of their messages are still unread
    waiting = dict(db.session.query(Message.sender_id, db.func.count(Message.id))
                   .filter(Message.student_id == user.id, Message.from_teacher.is_(True), NOT_NOTICE,
                           Message.seen_by_student.is_(False), Message.hidden_for_student.is_(False))
                   .group_by(Message.sender_id).all())
    teachers = [{'teacher': t, 'online': t.online, 'unread': waiting.get(t.id, 0)} for t in M.teachers_for_student()]
    return {'items': items, 'pinned': pinned, 'unread_ids': unread_ids, 'max_len': M.max_len(),
            'teachers': teachers, 'teacher': teacher}


def teacher_panel(choice='all', mark_seen=True):
    """The messages side panel for a teacher. choice 'all' (the default) shows every
    student's messages together, newest at the bottom, each with a Reply button;
    a student's id shows just that conversation, with a reply box. What is shown
    is marked seen. The menu lists every student, unread first."""
    rows = M.inbox(current_user)
    staff = staff_picker(current_user)
    if choice == 'teachers' or (isinstance(choice, str) and choice[:1] == 't' and choice[1:].isdigit()):
        return teachers_view(rows, staff, choice, mark_seen)
    try:
        student_id = int(choice)
    except (TypeError, ValueError):
        student_id = None
    chosen = next((r for r in rows if r['student'].id == student_id), None) if student_id else None
    if chosen is None:
        items = M.everyone(unread=M.unread_by_teacher(current_user), teacher=current_user)
        unread_ids = M.unseen_ids(current_user, items)
        if mark_seen:
            M.mark_messages_seen_by_teachers(current_user, items)
            for r in rows:
                r['unread'] = M.unread_from(current_user, r['student'].id)
        return {'rows': rows, 'student': None, 'items': items, 'unread_ids': unread_ids, 'staff': staff,
                'others_unread': sum(r['unread'] for r in rows), 'max_len': M.max_len(), 'everyone': True}
    student = chosen['student']
    items = M.conversation(student.id, limit=30, unread=M.unread_by_teacher(current_user), teacher=current_user)
    unread_ids = M.unseen_ids(current_user, items)
    if mark_seen:
        M.mark_seen_by_teachers(current_user, student.id)
        chosen['unread'] = 0
    #other students waiting for an answer, most recent first: the "new from ..." button
    waiting = sorted((r for r in rows if r['unread']), key=lambda r: r['last'].created, reverse=True)
    return {'rows': rows, 'student': student, 'items': items, 'unread_ids': unread_ids, 'staff': staff,
            'others_unread': sum(r['unread'] for r in rows), 'waiting': waiting,
            'max_len': M.max_len(), 'everyone': False}


def staff_picker(me):
    """The Teachers part of a teacher's picker: every other teacher (online first) with how
    many of their messages are still unread, and the unread total."""
    from .models import unread_staff
    waiting = M.staff_unread_by_sender(me)
    teachers = [{'teacher': t, 'online': t.online, 'unread': waiting.get(t.id, 0)} for t in M.other_teachers(me)]
    return {'teachers': teachers, 'unread': unread_staff(me.id)}


def teachers_view(rows, staff, choice, mark_seen=True):
    """Messages between teachers in the side panel: all of them ('teachers'), or with one
    other teacher ('t<id>'), and a box to write to the teachers checked under it."""
    try:
        other = M.staff_choice(current_user, choice)
    except M.MessageError:
        other = None  # e.g. a teacher since deleted, remembered in this browser
    items = M.teachers_thread(current_user, other)
    unread_ids = M.staff_unseen_ids(current_user, items)
    if mark_seen and unread_ids:
        M.mark_staff_seen(current_user, items)
        staff = staff_picker(current_user)
    return {'rows': rows, 'student': None, 'items': items, 'unread_ids': unread_ids, 'staff': staff,
            'teachers_view': True, 'other': other, 'max_len': M.max_len(), 'everyone': False}


# ---------------------------------------------------------------- both

#pages ask every 30 seconds whether anything new has arrived: unread counts for the two
#side panels' buttons, the newest ids (a panel reloads when they change), and a short
#preview of the newest unread item for the pop-up shown while a panel is hidden
@messages_bp.route('/messages/poll', methods=['GET'])
@login_required
def poll():
    #a quiz of theirs that has just opened (teachers take quizzes too): its notice comes with this check-in
    from app.qgen.services import announce_opened
    try:
        announce_opened(student_id=current_user.id)
    except Exception as exc:  # never let it break the check-in
        db.session.rollback()
        current_app.logger.error('announcing opened quizzes failed: {}'.format(exc))
    if current_user.is_admin:
        mine = Message.query.filter(Message.from_teacher.is_(False), for_teacher(current_user.id))
        unseen = ~seen_by(current_user.id)
        #a teacher's notices: about the students, and about quizzes they take themselves
        notice_q, notice_unseen = Message.query.filter(teacher_notices(current_user.id)), unread_teacher_notices(current_user.id)
        unread, notices = unread_messages_for_teacher(current_user.id), unread_notices_for_teachers(current_user.id)
    else:
        mine = Message.query.filter(Message.student_id == current_user.id, Message.from_teacher.is_(True),
                                    Message.hidden_for_student.is_(False))
        unseen = Message.seen_by_student.is_(False)
        notice_q, notice_unseen = mine.filter(IS_NOTICE), unseen
        unread, notices = unread_for_student(current_user.id), unread_notices_for_student(current_user.id)
    newest = lambda q: q.order_by(Message.id.desc()).first()
    latest, latest_notice = newest(mine.filter(NOT_NOTICE)), newest(notice_q)
    new_msg, new_notice = newest(mine.filter(NOT_NOTICE, unseen)), newest(notice_q.filter(notice_unseen))
    if current_user.is_admin:
        #a quiz for the teacher themselves pops up ahead of the notices about students
        new_notice = newest(Message.query.filter(own_notices(current_user.id), Message.seen_by_student.is_(False))) or new_notice
    latest_id, msg_preview = latest.id if latest else 0, preview(new_msg)
    if current_user.is_admin:
        #messages from other teachers count as messages too: the newest of either kind pops up
        from .models import StaffMessage, staff_for, staff_seen_by
        staff = StaffMessage.query.filter(staff_for(current_user.id))
        newest_staff = staff.order_by(StaffMessage.id.desc()).first()
        new_staff = staff.filter(StaffMessage.sender_id != current_user.id, ~staff_seen_by(current_user.id)) \
            .order_by(StaffMessage.id.desc()).first()
        latest_id = '{}-{}'.format(latest_id, newest_staff.id if newest_staff else 0)
        if new_staff and (new_msg is None or new_staff.created >= new_msg.created):
            msg_preview = staff_preview(new_staff)
    return jsonify(unread=unread, notices=notices,
                   latest=latest_id, latest_notice=latest_notice.id if latest_notice else 0,
                   message_preview=msg_preview, notice_preview=preview(new_notice),
                   messages_state=messages_state(), notices_state=notices_state(),
                   watch=live.state(request.args.get('watch')), review=review_waiting(), online=online_now(),
                   quizzes=new_quizzes(current_user.id))


def online_now():
    """For teachers: how many people are online (the count in the top bar)."""
    if not current_user.is_admin:
        return None
    from datetime import datetime
    return User.query.filter(User.online_condition(datetime.now())).count()


def review_waiting():
    """For teachers: quizzes waiting for grading (the count next to Grading)."""
    if not current_user.is_admin:
        return None
    from app.qgen.models import CQuiz
    return CQuiz.query.filter_by(needs_review=True, completed=False).count()


def messages_state():
    """Changes whenever what this person's Messages panel shows changes: a message
    written or deleted, pinned or unpinned, or removed from a student's view. Open
    panels reload when it changes, so a pin shows on every screen without a reload."""
    q = Message.query.filter(NOT_NOTICE)
    if current_user.is_admin:
        q = q.filter(for_teacher(current_user.id))
    else:
        q = q.filter(Message.student_id == current_user.id,
                     db.or_(Message.hidden_for_student.is_(False), Message.pinned.is_(True)))
    #worked out by the database: a poll doesn't read every message
    state = ':'.join(str(v or 0) for v in q.with_entities(
        db.func.count(Message.id), db.func.max(Message.id),
        db.func.sum(db.case((Message.pinned.is_(True), Message.id), else_=0)),
        db.func.sum(db.case((Message.hidden_for_student.is_(True), Message.id), else_=0))).one())
    if not current_user.is_admin:
        #a student's panel lists the teachers, online ones marked
        state += ':' + ','.join(str(t.id) for t in M.teachers_for_student() if t.online)
    else:
        #and a teacher's has the messages between teachers
        state += ':' + M.staff_state(current_user)
    return state


def notices_state():
    """The same for the Notices panel: a notice added or cleared."""
    q = Message.query.filter(IS_NOTICE)
    q = q.filter(db.or_(db.and_(Message.from_teacher.is_(False), ~cleared_by(current_user.id)), own_notices(current_user.id))) \
        if current_user.is_admin else q.filter(Message.from_teacher.is_(True), Message.student_id == current_user.id)
    return ':'.join(str(v or 0) for v in q.with_entities(
        db.func.count(Message.id), db.func.max(Message.id), db.func.sum(Message.id)).one())


def staff_preview(m):
    """The pop-up for a message from another teacher: "Open messages" shows it (view)."""
    body = m.body if len(m.body) <= 90 else m.body[:87].rstrip() + '…'
    return {'id': 's{}'.format(m.id), 'from': m.sender.shown_name if m.sender else 'a teacher', 'text': body,
            'view': 't{}'.format(m.sender_id) if m.sender_id else 'teachers'}


def preview(m):
    """Who and the first words, for the pop-up (the page shows it as plain text)."""
    if not m:
        return None
    who = (m.sender.shown_name if m.sender else 'Teacher') if m.from_teacher else m.student.shown_name
    body = m.body if len(m.body) <= 90 else m.body[:87].rstrip() + '…'
    return {'id': m.id, 'from': None if m.kind == 'notice' else who, 'text': body}
