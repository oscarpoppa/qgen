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


def _no_key():
    flash('Scanning workbook pages needs the AI helper, which isn’t set up (no API key).', 'error')
    return redirect(url_for('qgen.list_vquizzes'))


def _mine(job_id):
    """The teacher's own scan, or 404 (someone else's scans aren't theirs to see)."""
    job = db.session.get(ScanJob, job_id)
    if job is None or job.author_id != current_user.id:
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
    jobs = ScanJob.query.filter_by(author_id=current_user.id).order_by(ScanJob.updated_at.desc()).all()
    return render_template('scan_start.html', title='Scan workbook pages', jobs=jobs, max_pages=SC.MAX_PAGES)


@qgen_bp.route('/quiz/scan/new', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_upload():
    if not _key():
        return _no_key()
    try:
        pages = SC.load_pages(request.files.getlist('pages'))
    except SC.ScanError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('qgen.scan_start'))
    job = SC.create_job(current_user, request.form.get('name', ''), pages)
    data = SC.get_data(job)
    data['name'] = job.name
    data['folder'] = job.name
    SC.put_data(job, data)
    db.session.commit()
    current_app.logger.info('{} scanned {} page(s) of "{}" (scan {})'.format(current_user.username, job.pages, job.name, job.id))
    SC.start_reading(job, _key(), current_user.id)
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


@qgen_bp.route('/quiz/scan/<int:job_id>/status', methods=['GET'])
@login_required
@pw_check
@admin_only
def scan_status(job_id):
    job = _mine(job_id)
    pages = SC.get_data(job)['pages']
    return jsonify(reading=_reading(job), pages=[{'n': p['n'], 'state': p['state'], 'error': p.get('error')} for p in pages])


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
    return redirect(url_for('qgen.scan_review', job_id=job.id))


def review_page(job, data, problems=None, status=200):
    reading = _reading(job)
    checks = {}
    if not reading:
        for page in data['pages']:
            for i, item in enumerate(page.get('items') or []):
                checks[(page['n'], i)] = SC.check_item(item)
    return render_template('scan_review.html', title='Scan: {}'.format(job.name), job=job, data=data, reading=reading,
                           checks=checks, problems=problems or {}, uses=SC.use_choices(data), leads=SC.lead_of(data),
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
        flash('Draft kept. You can come back to it from “Scan workbook pages”.', 'success')
        return redirect(url_for('qgen.scan_review', job_id=job.id))
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
                            'problems': made['problems'], 'pictures': made['pictures'], 'folder': data.get('folder')}
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
    return render_template('scan_done.html', title='Scanned: {}'.format(done['name']), done=done, quizzes=quizzes)
