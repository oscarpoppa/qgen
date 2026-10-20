"""Pages for Scan workbook pages (app/qgen/scan.py): upload, reading progress, the draft,
Save and Discard. Teachers only, and only with an AI key."""
import copy

from flask import flash, render_template, redirect, url_for, request, current_app, abort, jsonify, send_file, session
from flask_login import current_user, login_required
from markupsafe import Markup

from . import db, qgen_bp
from . import scan as SC
from .models import ScanJob, VQuiz, RETAKE_RULES
from app.user.routes import admin_only, pw_check
from app.jsoncsrf import json_csrf_ok, post_form_only


def _key():
    return current_app.config.get('ANTHROPIC_API_KEY')


from app.user.models import User


def _no_key():
    flash('Scanning workbook pages needs the AI helper, which isn’t set up (no API key).', 'error')
    return redirect(url_for('qgen.list_vquizzes'))


def _mine(job_id):
    """A scan, for any teacher (the routes are teachers only), or 404. Every teacher sees every
    unfinished scan on the Dashboard, so each can open or discard it (the owner, 2026-10-20; it
    was the author's alone)."""
    job = db.session.get(ScanJob, job_id)
    if job is None:
        abort(404)
    return job


def _reading(job):
    return job.status == 'reading' and job.updated_at > SC.datetime.now() - SC.STALE


@qgen_bp.route('/quiz/scan', methods=['GET'])
@login_required
@pw_check
@admin_only
def scan_start():
    if not _key():
        return _no_key()
    #(every teacher's unfinished scans, like the Dashboard's pop-over: the owner, 2026-10-20)
    jobs = ScanJob.query.order_by(ScanJob.updated_at.desc()).all()
    #(the folder each scan's pages came from, if any: the owner, 2026-10-19)
    folders = {j.id: SC.get_data(j).get('from_folder') for j in jobs}
    #(each scan's kind, with its mark: the owner, 2026-10-19)
    kinds = {x['job'].id: x for x in scan_progress_data(current_user)}
    return render_template('scan_start.html', title='Scan workbook pages', jobs=jobs, folders=folders, kinds=kinds, max_pages=SC.MAX_PAGES)


def _elapsed(data):
    since = data.get('reading_since')
    try:
        return max(0, int((SC.datetime.now() - SC.datetime.fromisoformat(since)).total_seconds())) if since else 0
    except ValueError:
        return 0


def scan_progress_data(user):
    """Every teacher's unfinished scans, for the Dashboard's chip and pop-over (all teachers see
    them all: the owner, 2026-10-20; it was this teacher's own): each with how far the reading
    has got (the owner, 2026-10-18)."""
    out = []
    for job in ScanJob.query.order_by(ScanJob.updated_at.desc()).all():
        pages = SC.get_data(job).get('pages') or []
        now = next((p['n'] for p in pages if p.get('state') == 'reading'), None)
        data = SC.get_data(job)
        reading = _reading(job)
        kept = data.get('kept_at')
        #(who started it: every teacher sees every scan; the owner, 2026-10-20)
        author = db.session.get(User, job.author_id)
        out.append({'job': job, 'total': len(pages), 'reading': reading, 'now': now,
                    'by': author.shown_name if author else '',
                    #(seconds read so far, for the running timer: the owner, 2026-10-20)
                    'elapsed': _elapsed(data) if reading else 0,
                    'from_folder': data.get('from_folder'),
                    'done': sum(1 for p in pages if p.get('state') == 'done'),
                    'failed': sum(1 for p in pages if p.get('state') == 'error'),
                    #(reading, ready, paused, stopped or draft, each with its own mark: the owner, 2026-10-19)
                    'kind': SC.scan_kind(data, reading), 'pausing': reading and bool(data.get('pausing')),
                    'kept_at': SC.datetime.fromisoformat(kept) if kept else None,
                    'kept_today': bool(kept) and kept[:10] == SC.datetime.now().date().isoformat()})
    return out


@qgen_bp.route('/quiz/scan/progress', methods=['GET'])
@login_required
@pw_check
@admin_only
def scan_progress():
    """The Dashboard's scans card, as it stands now (static/js/scanprogress.js asks while reading)."""
    scans = scan_progress_data(current_user)
    return jsonify(reading=any(x['reading'] for x in scans), html=render_template('_scan_progress.html', scans=scans))


@qgen_bp.route('/quiz/scan/new', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_upload():
    if not _key():
        return _no_key()
    try:
        #(a whole folder comes in its own field: the owner, 2026-10-19)
        from_folder = [f for f in request.files.getlist('folder_pages') if f.filename]
        pages, skipped = SC.load_pages(from_folder or request.files.getlist('pages'), folder=bool(from_folder))
    except SC.ScanError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('qgen.scan_start'))
    if skipped:
        flash('Skipped {} file{} in the folder that {} a photo or PDF.'.format(
            len(skipped), '' if len(skipped) == 1 else 's', 'isn’t' if len(skipped) == 1 else 'aren’t'), 'info')
    job = SC.create_job(current_user, request.form.get('name', ''), pages)
    data = SC.get_data(job)
    data['name'] = job.name
    #(the folder the pages came from, for the reading card and the Dashboard: the owner, 2026-10-19)
    if from_folder:
        data['from_folder'] = ' '.join(request.form.get('from_folder', '').split())[:128] or 'a folder'
    #(no folder made for each scan: its problems and quizzes go in Uncategorized unless the
    #draft's Folder is filled in: the owner, 2026-10-18)
    data['folder'] = ''
    SC.put_data(job, data)
    db.session.commit()
    current_app.logger.info('{} scanned {} page(s) of "{}" (scan {})'.format(current_user.username, job.pages, job.name, job.id))
    SC.start_reading(job, _key(), current_user.id)
    #(Resume from the Dashboard's scans pop-over: back there, the owner 2026-10-19)
    if request.args.get('back') == 'dashboard':
        return redirect(url_for('qgen.dashboard'))
    return redirect(url_for('qgen.scan_review', job_id=job.id))


@qgen_bp.route('/quiz/scan/<int:job_id>/page/<int:n>', methods=['GET'])
@login_required
@pw_check
@admin_only
def scan_page_image(job_id, n):
    job = _mine(job_id)
    if not 1 <= n <= job.pages:
        abort(404)
    return send_file(SC.page_file(job.id, n), mimetype='image/jpeg', max_age=0)


@qgen_bp.route('/quiz/scan/<int:job_id>/thumb/<int:n>', methods=['GET'])
@login_required
@pw_check
@admin_only
def scan_page_thumb(job_id, n):
    """A small picture of page n, private like the page itself (the owner, 2026-10-18)."""
    job = _mine(job_id)
    if not 1 <= n <= job.pages:
        abort(404)
    return send_file(SC.thumb_file(job.id, n), mimetype='image/jpeg', max_age=0)


@qgen_bp.route('/quiz/scan/<int:job_id>/status', methods=['GET'])
@login_required
@pw_check
@admin_only
def scan_status(job_id):
    job = _mine(job_id)
    data = SC.get_data(job)
    pages = data['pages']
    #(times for the page's timer, with the server's own time so a computer's clock being off doesn't matter)
    return jsonify(reading=_reading(job), now=SC.datetime.now().isoformat(timespec='seconds'), since=data.get('reading_since'),
                   pages=[{'n': p['n'], 'state': p['state'], 'error': p.get('error'), 'since': p.get('since')} for p in pages])


@qgen_bp.route('/quiz/scan/<int:job_id>/read', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_read(job_id):
    """Read the pages not read yet (or that failed)."""
    job = _mine(job_id)
    if not _key():
        return _no_key()
    SC.start_reading(job, _key(), current_user.id)
    #(Resume from the Dashboard's scans pop-over: back there, the owner 2026-10-19)
    if request.args.get('back') == 'dashboard':
        return redirect(url_for('qgen.dashboard'))
    return redirect(url_for('qgen.scan_review', job_id=job.id))


def review_page(job, data, problems=None, status=200):
    reading = _reading(job)
    checks = {}
    if not reading:
        #(the names the quizzes and problems will get, from the workbook's name)
        SC.apply_names(data)
        for page in data['pages']:
            for i, item in enumerate(page.get('items') or []):
                checks[(page['n'], i)] = SC.check_item(item)
    return render_template('scan_review.html', title='Scan: {}'.format(job.name), job=job, data=data, reading=reading,
                           kind=SC.scan_kind(data, reading),
                           checks=checks, problems=problems or {},
                           reused=SC.reused_as(data) if not reading else {},
                           matches=SC.reused_as(data, ignore_new=True) if not reading else {}, uses=SC.use_choices(data), leads=SC.lead_of(data),
                           qtypes={k: SC.REGISTRY[k].label for k in SC.QTYPES}, kinds=SC.SCAN_KINDS,
                           unread=[p['n'] for p in data['pages'] if p['state'] != 'done']), status


@qgen_bp.route('/quiz/scan/<int:job_id>', methods=['GET'])
@login_required
@pw_check
@admin_only
def scan_review(job_id):
    job = _mine(job_id)
    return review_page(job, SC.get_data(job))


@qgen_bp.route('/quiz/scan/<int:job_id>', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_save(job_id):
    """Keep draft, or Save: make the problems and quizzes."""
    job = _mine(job_id)
    if _reading(job):
        flash('Some pages are still being read. Please wait until they’re done.', 'error')
        return redirect(url_for('qgen.scan_review', job_id=job.id))
    data = SC.update_from_form(SC.get_data(job), request.form)
    SC.put_data(job, data)
    db.session.commit()
    if request.form.get('action') != 'save':
        #(a draft the teacher kept, shown as such among the scans: the owner, 2026-10-19)
        data['kept_at'] = SC.datetime.now().isoformat(timespec='seconds')
        SC.put_data(job, data)
        db.session.commit()
        flash('Draft kept. You can come back to it from “Scan workbook pages”.', 'success')
        return redirect(url_for('qgen.scan_review', job_id=job.id))
    #(the quizzes and problems named after the workbook, before anything is made: the owner, 2026-10-19)
    data['_plan'] = SC.apply_names(data)
    problems = SC.check_all(data)
    if problems:
        flash('Nothing was saved yet: please fix the items marked below.', 'error')
        return review_page(job, data, problems, 400)
    try:
        made = SC.save_all(job, data, current_user)
    except SC.ScanError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return review_page(job, data, {}, 400)
    current_app.logger.info('{} saved scan {} "{}": {} quiz(zes), {} problem(s), {} picture(s)'.format(
        current_user.username, job.id, job.name, len(made['quizzes']), made['problems'], len(made['pictures'])))
    session['scan_done'] = {'name': data.get('name') or job.name, 'quizzes': [q.id for q in made['quizzes']],
                            'problems': made['problems'], 'reused': made.get('reused', 0), 'pictures': made['pictures'], 'folder': data.get('folder')}
    SC.remove_job(job)
    return redirect(url_for('qgen.scan_done'))


@qgen_bp.route('/quiz/scan/<int:job_id>/check', methods=['POST'])
@login_required
@pw_check
@admin_only
def scan_check(job_id):
    """One item as it stands on the page: its problems, warnings and three versions (nothing saved)."""
    if not json_csrf_ok():
        return jsonify(ok=False, error='Your session expired. Please reload the page.'), 400
    job = _mine(job_id)
    data = SC.update_from_form(copy.deepcopy(SC.get_data(job)), request.form)
    try:
        n, i = int(request.form.get('page', '')), int(request.form.get('item', ''))
        item = data['pages'][n - 1]['items'][i]
    except (ValueError, IndexError, KeyError):
        return jsonify(ok=False, error='That item isn’t on this scan.'), 400
    result = SC.check_item(item)
    return jsonify(ok=True, html=render_template('_scan_check.html', check=result, item=item))


@qgen_bp.route('/quiz/scan/<int:job_id>/pause', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_pause(job_id):
    """Pause the reading after the page being read; Resume goes on (the owner, 2026-10-19; it was Cancel)."""
    job = _mine(job_id)
    SC.pause_reading(job, _reading(job))
    current_app.logger.info('{} paused reading scan {} "{}"'.format(current_user.username, job.id, job.name))
    if request.args.get('back') == 'dashboard':
        return redirect(url_for('qgen.dashboard'))
    return redirect(url_for('qgen.scan_review', job_id=job.id))


@qgen_bp.route('/quiz/scan/<int:job_id>/discard', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_discard(job_id):
    job = _mine(job_id)
    name = job.name
    SC.remove_job(job)
    flash('Discarded the scan “{}”. Nothing from it was saved.'.format(name), 'success')
    current_app.logger.info('{} discarded scan {} "{}"'.format(current_user.username, job_id, name))
    #(discarded from the Dashboard's scans pop-over: back there, the owner 2026-10-18)
    if request.args.get('back') == 'dashboard':
        return redirect(url_for('qgen.dashboard'))
    return redirect(url_for('qgen.scan_start'))


@qgen_bp.route('/quiz/scan/done', methods=['GET'])
@login_required
@pw_check
@admin_only
def scan_done():
    done = session.get('scan_done')
    if not done:
        return redirect(url_for('qgen.scan_start'))
    quizzes = [q for q in (db.session.get(VQuiz, i) for i in done['quizzes']) if q]
    from . import layout as quiz_layout
    return render_template('scan_done.html', title='Scanned: {}'.format(done['name']), done=done, quizzes=quizzes, quiz_layout=quiz_layout)
