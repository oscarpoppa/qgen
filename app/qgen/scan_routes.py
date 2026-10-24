"""Pages for Scan workbook pages (app/qgen/scan.py): upload, reading progress, the draft,
Save and Discard. Teachers only, and only with an AI key."""
import copy
import json

from flask import flash, render_template, redirect, url_for, request, current_app, abort, jsonify, send_file, session
from flask_login import current_user, login_required
from markupsafe import Markup

from . import db, qgen_bp
from . import scan as SC
from .models import ScanJob, ScanFolder, VQuiz, RETAKE_RULES
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
    kinds = {x['job'].id: x for x in scan_progress_data(current_user, put_away=None)}
    #(the ones put away have a card of their own, under the others: the owner, 2026-10-20)
    away = [j for j in jobs if kinds.get(j.id, {}).get('put_away')]
    jobs = [j for j in jobs if not kinds.get(j.id, {}).get('put_away')]
    #the stash's folders (the owner, 2026-10-23): shared by all teachers, seen only here; one open at a time (?stash=)
    from app import folder_tree as FT
    stash_folders = ScanFolder.query.order_by(ScanFolder.name).all()
    root, flat, nodes = FT.tree(stash_folders, lambda f: f.name, away, {j.id: [j.folder_id] for j in away if j.folder_id})
    view, node = FT.view_of(request.args.get('stash'), nodes, default='all')
    shown = away if view == 'all' else root['items'] if view == 'main' else FT.subtree(node)
    return render_template('scan_start.html', title='Scan workbook pages', jobs=jobs, away=away, folders=folders, kinds=kinds,
                           max_pages=SC.max_pages(), stash_root=root, stash_flat=flat, stash_nodes=nodes, stash_view=view,
                           stash_node=node, stash_shown=shown, stash_path=FT.path(nodes, node) if node else [],
                           #(the Move dialog's folders, each [id, name, depth, icon], in the side list's order)
                           stash_pick_rows=[[f.id, f.name, depth, 'folder'] for f, depth in flat],
                           #(the open folder's own Move to: every folder but itself and the ones inside it)
                           stash_move_rows=[[f.id, f.name, depth, 'folder'] for f, depth in flat if not node or f.id not in _folder_ids(node)],
                           stash_path_ids=[f.id for f in FT.path(nodes, node)] if node else [])


def _folder_ids(node):
    """The ids of a stash folder and of every folder inside it."""
    ids = {node['folder'].id}
    for child in node['folders']:
        ids |= _folder_ids(child)
    return ids


def _elapsed(data):
    since = data.get('reading_since')
    try:
        return max(0, int((SC.datetime.now() - SC.datetime.fromisoformat(since)).total_seconds())) if since else 0
    except ValueError:
        return 0


def scan_progress_data(user, put_away=False):
    """Every teacher's unfinished scans, for the Dashboard's chip and pop-over (all teachers see
    them all: the owner, 2026-10-20; it was this teacher's own): each with how far the reading
    has got (the owner, 2026-10-18). put_away: False leaves out the scans put away (the owner,
    2026-10-20: they're only in Scan workbook pages' Put away card), None takes them all."""
    out = []
    for job in ScanJob.query.order_by(ScanJob.updated_at.desc()).all():
        data = SC.get_data(job)
        if put_away is False and data.get('put_away'):
            continue
        pages = data.get('pages') or []
        now = next((p['n'] for p in pages if p.get('state') == 'reading'), None)
        reading = _reading(job)
        kept = data.get('kept_at')
        #(who started it: every teacher sees every scan; the owner, 2026-10-20)
        author = db.session.get(User, job.author_id)
        out.append({'job': job, 'total': len(pages), 'reading': reading, 'now': now,
                    #(not for your own: "by NAME" on the status line read as if that person couldn't
                    #read the page; another teacher's scan says "Started by NAME" on a line of its own,
                    #the owner 2026-10-22)
                    'by': author.shown_name if author and author.id != user.id else '',
                    #(seconds read so far, for the running timer: the owner, 2026-10-20)
                    'elapsed': _elapsed(data) if reading else 0,
                    'from_folder': data.get('from_folder'),
                    'done': sum(1 for p in pages if p.get('state') == 'done'),
                    'failed': sum(1 for p in pages if p.get('state') == 'error'),
                    'slow': sum(1 for p in pages if p.get('state') == 'error' and p.get('timed_out')),
                    #(reading, ready, paused, stopped or draft, each with its own mark: the owner, 2026-10-19)
                    'kind': SC.scan_kind(data, reading), 'pausing': reading and bool(data.get('pausing')),
                    'kept_at': SC.datetime.fromisoformat(kept) if kept else None,
                    'put_away': bool(data.get('put_away')),
                    'kept_today': bool(kept) and kept[:10] == SC.datetime.now().date().isoformat()})
    return out


@qgen_bp.route('/quiz/scan/progress', methods=['GET'])
@login_required
@pw_check
@admin_only
def scan_progress():
    """The Dashboard's scans card, as it stands now (static/js/scanprogress.js asks while reading)."""
    #(the scans put away too, in their own list under Current scans: the owner, 2026-10-20)
    scans = [x for x in scan_progress_data(current_user, put_away=None) if not x['put_away']]
    return jsonify(reading=any(x['reading'] for x in scans), count=_count_words(len(scans)),
                   html=render_template('_scan_progress.html', scans=scans))


def _count_words(n):
    return '{} scan{}'.format(n, '' if n == 1 else 's')


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
    #(back on Scan workbook pages, the new scan in its Current scans, which keeps itself up to date
    #while it's read; its own page opens from there: the owner, 2026-10-20)
    return redirect(url_for('qgen.scan_start'))


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
    #(from Scan workbook pages' Current scans: back there, the owner 2026-10-20)
    if request.args.get('back') == 'scans':
        return redirect(url_for('qgen.scan_start'))
    return redirect(url_for('qgen.scan_review', job_id=job.id))


def review_page(job, data, problems=None, status=200):
    reading = _reading(job)
    checks = {}
    if not reading:
        #(the names the quizzes and problems will get, from the workbook's name)
        SC.apply_names(data)
        for page in data['pages']:
            for i, item in enumerate(page.get('items') or []):
                checks[(page['n'], i)] = SC.checked_item(item)
    return render_template('scan_review.html', title='Scan: {}'.format(job.name), job=job, data=data, reading=reading,
                           kind=SC.scan_kind(data, reading), note_longest=SC.NOTE_LONGEST,
                           checks=checks, problems=problems or {},
                           reused=SC.reused_as(data) if not reading else {},
                           matches=SC.reused_as(data, ignore_new=True) if not reading else {}, uses=SC.use_choices(data), leads=SC.lead_of(data),
                           qtypes={k: SC.REGISTRY[k].label for k in SC.QTYPES}, kinds=SC.SCAN_KINDS,
                           place_of=SC.place_of, label_of=SC.label_of, no_place=SC.NO_PLACE,
                           missing=SC.missing_places(data) if not reading else [],
                           unread=[p['n'] for p in data['pages'] if p['state'] != 'done']), status


@qgen_bp.route('/quiz/scan/<int:job_id>', methods=['GET'])
@login_required
@pw_check
@admin_only
def scan_review(job_id):
    job = _mine(job_id)
    data = SC.get_data(job)
    page = review_page(job, data)
    #(checks done for this load are kept, so the next one is quick; not "Last changed", nothing
    #the teacher did changed; not while it's being read, the reader saves the draft then)
    #Only the checks are taken over: the page also fills in names it shows, which aren't saved here.
    if not _reading(job):
        stored = SC.get_data(job)
        for page_now, page_then in zip(data.get('pages') or [], stored.get('pages') or []):
            for item_now, item_then in zip(page_now.get('items') or [], page_then.get('items') or []):
                if 'check' in item_now:
                    item_then['check'] = item_now['check']
        kept = json.dumps(stored)
        if kept != job.data:
            job.data = kept
            db.session.commit()
    return page


@qgen_bp.route('/quiz/scan/<int:job_id>/page/<int:n>/again', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_read_again(job_id, n):
    """Read this page again (the owner, 2026-10-20): the review form is sent with it, so the
    changes made on the other pages are kept, as Keep draft would; this page's reading and
    changes are dropped, and it's read from the start with the teacher's note."""
    job = _mine(job_id)
    if not _key():
        return _no_key()
    if not 1 <= n <= job.pages:
        abort(404)
    if _reading(job):
        flash('Some pages are still being read. Please wait until they’re done.', 'error')
        return redirect(url_for('qgen.scan_review', job_id=job.id))
    data = SC.update_from_form(SC.get_data(job), request.form)
    SC.read_again(data, n, request.form.get('p{}-again_note'.format(n), ''))
    SC.put_data(job, data)
    db.session.commit()
    current_app.logger.info('{} asked for page {} of scan {} "{}" to be read again'.format(current_user.username, n, job.id, job.name))
    SC.start_reading(job, _key(), current_user.id)
    return redirect(url_for('qgen.scan_review', job_id=job.id))


@qgen_bp.route('/quiz/scan/<int:job_id>/page/<int:n>/places', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_find_places(job_id, n):
    """Find the boxes again (the owner, 2026-10-21): this page's answer boxes found again, without
    the AI; the review form is sent with it, so the other changes are kept."""
    job = _mine(job_id)
    if not 1 <= n <= job.pages:
        abort(404)
    if _reading(job):
        flash('Some pages are still being read. Please wait until they’re done.', 'error')
        return redirect(url_for('qgen.scan_review', job_id=job.id))
    data = SC.update_from_form(SC.get_data(job), request.form)
    SC.find_places_again(job.id, data['pages'][n - 1])
    SC.put_data(job, data)
    db.session.commit()
    current_app.logger.info('{} had the boxes on page {} of scan {} "{}" found again'.format(current_user.username, n, job.id, job.name))
    return redirect(url_for('qgen.scan_review', job_id=job.id))


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
    if request.form.get('action') == 'unstash':
        #(a stashed draft: the edits kept, and the scan back in Current scans: the owner, 2026-10-23)
        data['kept_at'] = SC.datetime.now().isoformat(timespec='seconds')
        SC.put_data(job, data)
        db.session.commit()
        SC.keep_corrections(job, data)
        SC.put_away(job, False)
        current_app.logger.info('{} unstashed the draft of scan {} "{}"'.format(current_user.username, job.id, job.name))
        flash('“{}” is back in Current scans, with your edits.'.format(job.name), 'success')
        return redirect(url_for('qgen.scan_start'))
    if request.form.get('action') != 'save':
        #(a draft the teacher kept, shown as such among the scans: the owner, 2026-10-19; Stash draft
        #keeps the edits and stashes it in one go, back on Scan workbook pages: the owner, 2026-10-21)
        data['kept_at'] = SC.datetime.now().isoformat(timespec='seconds')
        SC.put_data(job, data)
        db.session.commit()
        SC.keep_corrections(job, data)
        SC.put_away(job)
        current_app.logger.info('{} stashed the draft of scan {} "{}"'.format(current_user.username, job.id, job.name))
        flash('“{}” stashed, with your edits.'.format(job.name), 'success')
        return redirect(url_for('qgen.scan_start'))
    #(the quizzes and problems named after the workbook, before anything is made: the owner, 2026-10-19)
    data['_plan'] = SC.apply_names(data)
    problems = SC.check_all(data)
    if problems:
        flash('Nothing was saved yet: please fix the items marked below.', 'error')
        return review_page(job, data, problems, 400)
    #(boxes fixed by hand kept as tests of the box finder: the owner, 2026-10-22)
    SC.keep_corrections(job, data)
    try:
        made = SC.save_all(job, data, current_user)
    except SC.ScanError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return review_page(job, data, {}, 400)
    current_app.logger.info('{} saved scan {} "{}": {} quiz(zes), {} problem(s), {} picture(s)'.format(
        current_user.username, job.id, job.name, len(made['quizzes']), made['problems'], len(made['pictures'])))
    #(job: the scan's own pages are gone once it's saved, so Back skips them: the owner, 2026-10-20)
    session['scan_done'] = {'name': data.get('name') or job.name, 'job': job.id, 'quizzes': [q.id for q in made['quizzes']],
                            'problems': made['problems'], 'reused': made.get('reused', 0), 'pictures': made['pictures'], 'folder': data.get('folder')}
    #(the pages not saved stay, stashed under the same name; with none left the scan goes: the owner, 2026-10-22)
    left = SC.keep_leftovers(job, data)
    if left:
        db.session.commit()
        session['scan_done']['left'] = left
    else:
        SC.remove_job(job)
    return redirect(url_for('qgen.scan_done'))


@qgen_bp.route('/quiz/scan/<int:job_id>/helper', methods=['POST'])
@login_required
@pw_check
@admin_only
def scan_helper(job_id):
    """The Helper card's hints for the draft as it is in the form now (nothing is saved)."""
    if not json_csrf_ok():
        return jsonify(ok=False, error='Your session expired. Please reload the page.'), 400
    job = _mine(job_id)
    data = SC.update_from_form(SC.get_data(job), request.form)
    hints = SC.helper_hints(job, data, {'again': lambda n: url_for('qgen.scan_read_again', job_id=job.id, n=n),
                                        'drop': lambda n: url_for('qgen.scan_drop_page', job_id=job.id, n=n)})
    return jsonify(hints=hints)


@qgen_bp.route('/quiz/scan/<int:job_id>/page/<int:n>/drop', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_drop_page(job_id, n):
    """Discard one page that didn't make it (the owner, 2026-10-23); the review form is sent with it, so the
    changes made on the other pages are kept."""
    job = _mine(job_id)
    if _reading(job):
        flash('Some pages are still being read. Please wait until they’re done.', 'error')
        return redirect(url_for('qgen.scan_review', job_id=job.id))
    data = SC.update_from_form(SC.get_data(job), request.form)
    page = next((p for p in data.get('pages') or [] if p['n'] == n), None)
    if page is None or page.get('state') == 'done':
        abort(404)
    left = SC.drop_page(job, data, n)
    db.session.commit()
    current_app.logger.info('{} discarded page {} of scan {} "{}"'.format(current_user.username, n, job.id, job.name))
    if not left:
        SC.remove_job(job)
        db.session.commit()
        flash('That was the last page, so the scan “{}” is gone.'.format(job.name), 'success')
        return redirect(url_for('qgen.scan_start'))
    flash('Page {} was discarded.'.format(n), 'success')
    return redirect(url_for('qgen.scan_review', job_id=job.id))


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
    """Pause the reading after the pages being read; Resume goes on (the owner, 2026-10-19; it was Cancel)."""
    job = _mine(job_id)
    SC.pause_reading(job, _reading(job))
    current_app.logger.info('{} paused reading scan {} "{}"'.format(current_user.username, job.id, job.name))
    if request.args.get('back') == 'dashboard':
        return redirect(url_for('qgen.dashboard'))
    #(from Scan workbook pages' Current scans: back there, the owner 2026-10-20)
    if request.args.get('back') == 'scans':
        return redirect(url_for('qgen.scan_start'))
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


@qgen_bp.route('/quiz/scan/<int:job_id>/put-away', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_put_away(job_id):
    """Put away a paused or stopped scan, or a draft: out of Current scans into the Put away card (the owner, 2026-10-20)."""
    job = _mine(job_id)
    if _reading(job):
        flash('“{}” is being read. Pause it first, then stash it.'.format(job.name), 'error')
    else:
        SC.put_away(job)
        current_app.logger.info('{} put away scan {} "{}"'.format(current_user.username, job.id, job.name))
    #(from the Dashboard's scan pop-over: back there, the owner 2026-10-20)
    if request.args.get('back') == 'dashboard':
        return redirect(url_for('qgen.dashboard'))
    return redirect(url_for('qgen.scan_start'))


def _stash_back(folder_id=None):
    """Back to the Stashed scans card, on the folder that was open."""
    return redirect(url_for('qgen.scan_start', stash=folder_id) + '#scan-away' if folder_id else url_for('qgen.scan_start') + '#scan-away')


@qgen_bp.route('/quiz/scan/folders/new', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_new_folder():
    """A folder in the stash, inside the one open (the owner, 2026-10-23)."""
    from app import folder_tree as FT
    parent = request.form.get('parent') or None
    try:
        folder = SC.create_folder(request.form.get('name'), int(parent) if parent and parent.isdigit() else None)
    except FT.FolderError as exc:
        flash(str(exc), 'error')
        return _stash_back(parent)
    flash('Folder “{}” made.'.format(folder.name), 'success')
    return _stash_back(folder.id)


@qgen_bp.route('/quiz/scan/folders/<int:fid>/rename', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_rename_folder(fid):
    from app import folder_tree as FT
    folder = db.get_or_404(ScanFolder, fid)
    try:
        SC.rename_folder(folder, request.form.get('name'))
    except FT.FolderError as exc:
        flash(str(exc), 'error')
        return _stash_back(folder.id)
    flash('Folder renamed to “{}”.'.format(folder.name), 'success')
    return _stash_back(folder.id)


@qgen_bp.route('/quiz/scan/folders/<int:fid>/move', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_move_folder(fid):
    """A stash folder inside another, or out to the top (the owner, 2026-10-23: the standard folder menu's Move to)."""
    from app import folder_tree as FT
    folder = db.get_or_404(ScanFolder, fid)
    to = request.form.get('to') or ''
    if to and to != 'top' and not (to.isdigit() and db.session.get(ScanFolder, int(to))):
        abort(404)
    try:
        SC.move_folder(folder, to)
    except FT.FolderError as exc:
        flash(str(exc), 'error')
        return _stash_back(folder.id)
    flash('Moved “{}” to {}.'.format(folder.name, '“{}”'.format(db.session.get(ScanFolder, int(to)).name) if to.isdigit() else 'the top'), 'success')
    return _stash_back(folder.id)


@qgen_bp.route('/quiz/scan/folders/<int:fid>/delete', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_delete_folder(fid):
    folder = db.get_or_404(ScanFolder, fid)
    name, up = folder.name, folder.parent_id
    scans, inner = SC.delete_folder(folder)
    bits = [x for x in ('{} scan{}'.format(scans, '' if scans == 1 else 's') if scans else '',
                        '{} folder{}'.format(inner, '' if inner == 1 else 's') if inner else '') if x]
    flash('Deleted the folder “{}”.{}'.format(name, ' {} moved up.'.format(' and '.join(bits)) if bits else ''), 'success')
    return _stash_back(up)


@qgen_bp.route('/quiz/scan/<int:job_id>/move', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_move(job_id):
    """A stashed scan into a folder, or out to Uncategorized (the owner, 2026-10-23)."""
    job = db.get_or_404(ScanJob, job_id)
    to = request.form.get('to') or ''
    to = '' if to == 'top' else to  # (the dialog's Uncategorized row)
    if to and not (to.isdigit() and db.session.get(ScanFolder, int(to))):
        abort(404)
    SC.move_scan(job, to)
    flash('“{}” moved to {}.'.format(job.name, '“{}”'.format(db.session.get(ScanFolder, int(to)).name) if to else 'Uncategorized'), 'success')
    #(dragged onto a folder: the view stays where it was, so scans can be dragged one after another out of the folder open: the owner, 2026-10-23)
    if 'stay' in request.form:
        return _stash_back(request.form.get('stay') or None)
    return _stash_back(to or None)


@qgen_bp.route('/quiz/scan/<int:job_id>/take-out', methods=['POST'])
@login_required
@pw_check
@admin_only
@post_form_only
def scan_take_out(job_id):
    """Take a scan out of the Put away card, back into Current scans (the owner, 2026-10-20)."""
    job = _mine(job_id)
    SC.put_away(job, False)
    current_app.logger.info('{} took out scan {} "{}"'.format(current_user.username, job.id, job.name))
    #(from the Dashboard's scan pop-over: back there, the owner 2026-10-20)
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
