"""Scan workbook pages: photos or a PDF of a paper workbook become problems and quizzes.

1. Upload: the pages (any image QuizScan reads, or a PDF) are turned upright and kept at full
   size, with a smaller copy to show, in a private folder (SCAN_DIR, not under static) with a
   ScanJob row holding the draft as JSON.
2. Reading: QuizScan and the AI read up to READ_AT_ONCE pages at a time, in background
   threads (a page takes longer than a web request may), and the review page checks on it.
   Every AI call counts against the hourly limit, and is logged like the other AI buttons.
3. The draft: the teacher checks every page beside its picture, adjusts crop boxes,
   random values and settings. Nothing is saved until Save.
4. Save: everything is checked first; only then are the pictures cropped into the
   pictures folder and the problems and one quiz per page (or joined pages) made.

Exercises done on paper (drawing, coloring, circling) become Paper only problems with
their crop as the picture. A page that is only a picture is saved to the pictures folder
and can go in the picture section of a quiz or problem.
"""
import hashlib
import io
import json
import os
import random
import re
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

from flask import current_app

from app import tuning
from . import db
from .models import ScanJob, ScanFolder, VProblem, VQuiz, AICall
from .qtypes import get_qtype, REGISTRY
from . import friendly as F
from . import spread

STALE = timedelta(minutes=10)   # a page "reading" longer than this was cut off (the site restarted)
#(Settings > Technical settings > Scanning, the owner 2026-10-23)
def max_pages():
    """Pages in one batch."""
    return tuning.get('scan_pages')


def long_side():
    """Pixels: the page shown and searched for answer places (pictures are cut from the full-size one)."""
    return tuning.get('scan_long_side')


def keep_for():
    """Unfinished scans untouched this long are removed."""
    return timedelta(days=tuning.get('scan_keep_days'))


def page_minutes():
    """How long one page may take before it's stopped (the site's SCAN_PAGE_MINUTES config, when set, instead)."""
    return float(current_app.config.get('SCAN_PAGE_MINUTES') or tuning.get('scan_page_minutes'))


DRAWS = 200             # versions drawn to check a problem's random values
QTYPES = ('numeric', 'text', 'choice_one', 'choice_many', 'truefalse', 'essay')  # typed kinds a scanned item can be
VALUE_KEYS = ('name', 'kind', 'min', 'max', 'step', 'places', 'items', 'pick_n', 'formula', 'different_from', 'nonzero')
SCAN_KINDS = ('whole', 'decimal', 'list', 'calc')  # value kinds offered for workbook pages


class ScanError(Exception):
    """A problem to show the teacher, in plain words."""


# ---------------------------------------------------------------- files

def scan_root():
    return current_app.config['SCAN_DIR']


def job_dir(job_id):
    return os.path.join(scan_root(), str(int(job_id)))


def page_file(job_id, n):
    return os.path.join(job_dir(job_id), 'page-{}.jpg'.format(int(n)))


def thumb_file(job_id, n):
    """A small copy of page n (about 200 pixels tall), made when first asked for, and again
    after the page is straightened (the owner, 2026-10-18)."""
    from PIL import Image
    src = page_file(job_id, n)
    out = os.path.join(job_dir(job_id), 'thumb-{}.jpg'.format(int(n)))
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        with Image.open(src) as im:
            im = im.convert('RGB')
            im.thumbnail((200, 200))
            im.save(out, 'JPEG', quality=80)
    return out


def _natural(name):
    """Sort key for file names, numbers by their value: page2 before page10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name or '')]


def full_file(job_id, n):
    """Page n at full size (up to QuizScan's FULL_MAX): what QuizScan reads and pictures are cut
    from; page_file is the smaller copy shown and searched for answer places (the owner, 2026-10-20)."""
    return os.path.join(job_dir(job_id), 'full-{}.jpg'.format(int(n)))


def orig_file(job_id, n):
    """Page n as uploaded (full size, not yet straightened): kept once it's read, so the page can
    be read again from the start (the owner, 2026-10-20)."""
    return os.path.join(job_dir(job_id), 'orig-{}.jpg'.format(int(n)))


def _jpeg(im, quality=90):
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=quality)
    return buf.getvalue()


def save_page(job_id, n, im):
    """Page n's picture, kept twice: full size, and scaled down to long_side() for showing."""
    im = im.convert('RGB')
    im.save(full_file(job_id, n), 'JPEG', quality=90)
    small = im.copy()
    small.thumbnail((long_side(), long_side()))
    small.save(page_file(job_id, n), 'JPEG', quality=85)


class Pages(list):
    """The page pictures of an upload (JPEG bytes); .spreads: the (0-based) places of the ones that are half of a photo of two pages."""
    def __init__(self):
        super().__init__()
        self.spreads = set()


def load_pages(files, folder=False):
    """Uploaded files -> page pictures (JPEG bytes): upright, RGB, at full size (long side at
    most QuizScan's FULL_MAX). Any image QuizScan reads (the owner, 2026-10-20): photos of any
    kind (JPG, PNG, WebP, HEIC, AVIF, ...), TIFF pages, SVG drawings, camera RAW, and PDFs.
    Raises ScanError for files that can't be read or too many pages.
    folder: the files of a whole folder (the owner, 2026-10-19): taken in file-name order, and
    anything in it that isn't a picture or a PDF (notes, system files) is skipped, not an error.
    Returns (pages, names of the files skipped)."""
    import tempfile
    from werkzeug.utils import secure_filename
    from quizscan import images
    pages, skipped = Pages(), []
    if folder:
        files = sorted(files, key=lambda f: _natural(f.filename))

    def room(more=1):
        if len(pages) + more > max_pages():
            raise ScanError('That’s more than {} pages. Please put them in as smaller workbooks.'.format(max_pages()))

    #(QuizScan opens files by path, and tells many kinds apart by their names: each upload is
    #written under its own name in a private folder that's removed afterwards)
    with tempfile.TemporaryDirectory(prefix='qgen-scan-') as tmp:
        for i, f in enumerate(files):
            data = f.read()
            name = f.filename or 'a file'
            if not data:
                continue
            path = os.path.join(tmp, '{}-{}'.format(i, secure_filename(os.path.basename(name)) or 'page'))
            with open(path, 'wb') as out:
                out.write(data)
            if folder and not images.is_image_file(path):
                skipped.append(name)
                continue
            try:
                count = images.page_count(path)
                room(count)
                for n in range(1, count + 1):
                    im = images.load_full_page(path, n)
                    #(a photo of two facing pages is cut at the spine into two pages, left then right: the owner, 2026-10-23)
                    halves = spread.split(im)
                    if halves:
                        room(len(halves) - 1)
                        pages.spreads.update(range(len(pages), len(pages) + len(halves)))
                        pages.extend(_jpeg(half) for half in halves)
                    else:
                        pages.append(_jpeg(im))
            except images.QuizScanError as exc:
                if folder:
                    skipped.append(name)
                    continue
                raise ScanError(_reason(exc, path, name))
            finally:
                os.remove(path)
    if not pages:
        if folder:
            raise ScanError('That folder has no photos or PDFs to scan.')
        raise ScanError('Please choose at least one photo or PDF of a workbook page.')
    return pages, skipped


def _reason(exc, path, name):
    """QuizScan's words about a file, with its name as the teacher knows it (not the private copy's)."""
    return str(exc).replace(os.path.basename(path), '“{}”'.format(name))


def create_job(author, name, pages):
    """A new scan with these page pictures (JPEG bytes, full size), nothing read yet."""
    from PIL import Image
    job = ScanJob(author_id=author.id, name=(name or '').strip()[:128] or 'Workbook', pages=len(pages), status='new',
                  data=json.dumps({'pages': [dict({'n': i + 1, 'state': 'waiting'}, **({'spread': True} if i in getattr(pages, 'spreads', ()) else {}))
                                          for i in range(len(pages))]}))
    db.session.add(job)
    db.session.commit()
    #(a new scan's folder starts empty: anything left under its number from before, such as a page
    #kept as uploaded, isn't this scan's)
    shutil.rmtree(job_dir(job.id), ignore_errors=True)
    os.makedirs(job_dir(job.id), exist_ok=True)
    for i, data in enumerate(pages):
        with Image.open(io.BytesIO(data)) as im:
            save_page(job.id, i + 1, im)
    return job


def remove_job(job):
    shutil.rmtree(job_dir(job.id), ignore_errors=True)
    db.session.delete(job)
    db.session.commit()


def hand_over_jobs(user, to):
    """When a teacher's account is deleted: their unfinished scans go to the teacher deleting it
    (scans are shared by all teachers, so none is lost: the owner, 2026-10-20). With nobody to
    give them to, they're removed with their page files."""
    for job in ScanJob.query.filter_by(author_id=user.id).all():
        if to is not None and to.id != user.id:
            job.author_id = to.id
        else:
            shutil.rmtree(job_dir(job.id), ignore_errors=True)
            db.session.delete(job)


def remove_old_jobs(now=None):
    """Unfinished scans nobody has touched for a month. Returns how many. Not one in the Trash: it stays
    until it's deleted for good (the owner, 2026-10-25)."""
    now = now or datetime.now()
    old = ScanJob.query.filter(ScanJob.updated_at < now - keep_for(), ScanJob.status != TRASHED).all()
    for job in old:
        remove_job(job)
    return len(old)


TRASHED = 'trashed'   # a workbook in the Trash (the owner, 2026-10-25): its status


def trash_job(job, by=None):
    """A workbook moved to the Trash (the owner, 2026-10-25): when its last page is generated, or by
    Move to Trash. Its reading, if any, stops; its pages and draft are kept, so it can be viewed,
    restored (to the stash's Uncategorized) or deleted for good."""
    if job.status == 'reading':
        pause_reading(job, True, now=True)
    with page_lock(job.id) as data:
        if data is None:
            return
        data['trashed_at'] = datetime.now().isoformat(timespec='seconds')
        data['trashed_by'] = by.id if by is not None else None
        job.status = TRASHED


def restore_job(job):
    """Out of the Trash, into the stash's Uncategorized (the owner, 2026-10-25)."""
    with page_lock(job.id) as data:
        if data is None:
            return
        data.pop('trashed_at', None)
        data.pop('trashed_by', None)
        data['put_away'] = datetime.now().isoformat(timespec='seconds')
        job.status = 'ready'
        job.folder_id = None


def trashed_jobs():
    """The workbooks in the Trash, the latest first."""
    jobs = ScanJob.query.filter_by(status=TRASHED).all()
    return sorted(jobs, key=lambda j: get_data(j).get('trashed_at') or '', reverse=True)


def get_data(job):
    return json.loads(job.data or '{}')


def put_data(job, data):
    job.data = json.dumps(data)
    job.updated_at = datetime.now()


# ---------------------------------------------------------------- reading (the AI)

def start_reading(job, api_key, user_id, only=None):
    """Read the job's unread pages (and any that failed) in the background. False when
    it's already being read. only: these page numbers and no others, a page's own Read this page
    (the owner, 2026-10-25: it used to start every page waiting); None, Resume all."""
    now = datetime.now()
    data = get_data(job)
    if only:
        data['only'] = list(only)
    else:
        data.pop('only', None)
    data.pop('stopped', None)
    for p in data['pages']:
        if only and p['n'] not in only:
            continue
        if p['state'] == 'error':
            p['state'] = 'waiting'
        if p['state'] == 'waiting':
            p.pop('error', None)
    #(read again: no longer paused nor a kept draft, the owner 2026-10-19; nor put away, so it's in
    #Current scans while it's read, the owner 2026-10-20)
    for k in ('paused', 'pausing', 'kept_at', 'put_away'):
        data.pop(k, None)
    #(when this reading started, for the scan page's timer: the owner, 2026-10-18)
    data['reading_since'] = now.isoformat(timespec='seconds')
    #this reading's own mark: Cancel takes it away, and a reading started again gets a new one, so an
    #old reading still finishing a page stops instead of going on beside the new one
    import uuid
    run = data['run'] = uuid.uuid4().hex
    claimed = ScanJob.query.filter(ScanJob.id == job.id, db.or_(ScanJob.status != 'reading', ScanJob.updated_at < now - STALE)) \
        .update({'status': 'reading', 'updated_at': now, 'data': json.dumps(data)}, synchronize_session=False)
    db.session.commit()
    if not claimed:
        return False
    app = current_app._get_current_object()
    if app.testing:
        _read_all(app, job.id, api_key, user_id, run)  # tests wait for it
    else:
        threading.Thread(target=_read_all, args=(app, job.id, api_key, user_id, run), daemon=True).start()
    return True


#a page whose reading runs longer than this is stopped, and the scan goes on with the next one (the owner, 2026-10-23: the
#site's SCAN_PAGE_MINUTES setting, when set, instead); at the end the pages that didn't make it say why
PAGE_TOO_SLOW = ('This page took longer than {} minutes to read, so it was stopped and the workbook went on with the next page. '
                 'Press \u201cRead this page\u201d to read it again, or photograph just this page, closer up.')


READ_AT_ONCE = 3   # pages read at the same time (each takes a minute or so of AI calls: the owner, 2026-10-20);
                   # the site's SCAN_READ_AT_ONCE setting, when set, instead


_LOCKS, _LOCKS_LOCK = {}, threading.Lock()


def _job_lock(job_id):
    with _LOCKS_LOCK:
        return _LOCKS.setdefault(job_id, threading.RLock())


@contextmanager
def page_lock(job_id):
    """A scan's data, fresh and locked until it's written back (yields None when the scan is gone):
    pages read side by side, and Pause, each change their own part without undoing another's. (MySQL locks
    the row; SQLite, the sandbox's and the tests', has no row locks, so the reading threads of one process
    also take a lock of their own: two pages' writes at once lost one of them, the tests 2026-10-25.)"""
    with _job_lock(job_id):
        job = db.session.get(ScanJob, job_id, with_for_update=True, populate_existing=True)
        if job is None:
            db.session.rollback()
            yield None
            return
        data = get_data(job)
        states = [p.get('state') for p in data.get('pages') or []]
        try:
            yield data
        except BaseException:
            db.session.rollback()
            raise
        put_data(job, data)
        author = job.author_id
        db.session.commit()
    #a page started, read or failed: its teacher's open pages hear at once (scan rows are quiet
    #otherwise, app/push.py), so the scan's progress needs no asking every few seconds (the owner,
    #2026-10-20)
    if [p.get('state') for p in data.get('pages') or []] != states:
        from app import push
        push.tell(push._user_rooms(author))


_OLD_BUTTONS = re.compile('Press \u201c(?:Read the rest|Try again)\u201d(?: on it)? to (?:try it|read it) again')
_OLD_BUTTONS_LATER = re.compile('Press \u201c(?:Read the rest|Try again)\u201d(?: on it)? in a while')


def shown_error(text):
    """A page's saved error as it's shown now: one saved before the buttons were renamed names the button the
    page has now, \u201cRead this page\u201d (the owner, 2026-10-25: an old page said \u201cRead the rest\u201d, which
    isn't on the page)."""
    if not text:
        return text
    text = _OLD_BUTTONS.sub('Press \u201cRead this page\u201d to read it again', text)
    text = _OLD_BUTTONS_LATER.sub('Press \u201cRead this page\u201d in a while', text)
    return text.replace('\u201cRead the rest\u201d', '\u201cRead this page\u201d').replace('\u201cTry again\u201d', '\u201cRead this page\u201d')


#a page whose reading ran too long: what to do next, step by step (the owner, 2026-10-21)
PAGE_TOO_LONG = ('This page was read, but picking its random numbers ran too long, so it stopped. '
                 'Press \u201cRead this page\u201d to go on from there. If it stops again, photograph half the page at a time, closer up.')


def _read_page(app, job_id, n, api_key, user_id, reserved, cancel=None):
    """One page read in its own thread (read_one), with its own database session. cancel: set when
    the page ran over its time limit; the reading stops at its next step."""
    with app.app_context():
        try:
            job = db.session.get(ScanJob, job_id)
            if job is None:
                return None
            page = read_one(job, n, api_key, user_id, reserved, cancel)
            #(each problem checked now, while it's read, so the draft page opens quickly: the owner, 2026-10-21)
            if isinstance(page, dict) and page.get('state') == 'done':
                for item in page.get('items') or []:
                    checked_item(item)
            return page
        except Exception as exc:
            db.session.rollback()
            app.logger.exception('reading scan {} page {} failed: {}'.format(job_id, n, exc))
            return {'n': n, 'state': 'error', 'error': 'Something went wrong while reading this page. Press \u201cRead this page\u201d to read it again.'}
        finally:
            db.session.remove()


def _read_all(app, job_id, api_key, user_id, run=None):
    """Read a scan's waiting pages, up to READ_AT_ONCE at a time, each in its own thread. A page
    starts only when the hourly limit has room for its calls beside those the pages being read
    may still make. Pause (or the hourly limit) starts no more pages; those being read finish."""
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
    at_once = max(1, int(app.config.get('SCAN_READ_AT_ONCE') or READ_AT_ONCE))

    class NoWaitPool(ThreadPoolExecutor):
        def __exit__(self, *exc):
            #(a page that ran over its time may still be finishing: the scan is done without waiting for it)
            self.shutdown(wait=False)
            return False

    with app.app_context():
        running = {}    # future -> (page n, AI calls it may make, when it started, its cancel flag)
        limit = page_minutes() * 60

        def stop_all():
            #(Pause, Discard or read again meanwhile: the pages being read stop at their next step,
            #the owner 2026-10-24, CA10b)
            for v in running.values():
                v[3].set()
        try:
            #(room for a few pages that ran over their time and are still finishing, unnoticed, behind the ones being read)
            with NoWaitPool(max_workers=at_once + 8) as pool:
                stop = False      # the hourly limit was reached: no more pages start
                gone = False      # read again since (or stopped)
                while True:
                    #(looked at every time round, so Pause stops the pages being read even when all
                    #the threads are busy: the owner, 2026-10-24, CA10b; it used to look only while a
                    #thread was free)
                    start = None
                    blocked = False
                    with page_lock(job_id) as data:
                        if data is None:
                            stop_all()
                            return  # discarded meanwhile
                        if data.get('run') != run:
                            #read again since (or stopped): no more pages start here
                            gone = True
                            stop_all()
                        else:
                            gone = False
                            page = None
                            #(Stop this page: that page's reading stops at its next step, the others go on; it isn't
                            #started again in this reading, the owner 2026-10-25, CK2)
                            stopped = data.get('stopped') or []
                            for v in running.values():
                                if v[0] in stopped:
                                    v[3].set()
                            if not (stop or data.get('pausing')) and len(running) < at_once:
                                busy = {v[0] for v in running.values()}
                                #(a page still out with the AI from before a Pause isn't sent again until
                                #that reading has stopped: the owner, 2026-10-24, CA10a)
                                away = still_out(data, run, limit)
                                only = data.get('only')
                                waiting = [p for p in data['pages'] if p['state'] in ('waiting', 'reading') and p['n'] not in busy
                                           and (not only or p['n'] in only) and p['n'] not in stopped]
                                blocked = any(p['n'] in away for p in waiting)
                                page = next((p for p in waiting if p['n'] not in away), None)
                            if page is not None:
                                need = calls_for(page)
                                reserved = sum(v[1] for v in running.values())
                                #(no room beside the pages being read: wait for them; with none
                                #being read, read_one says it's waiting for the hourly limit)
                                if not running or ai_room(user_id, need, reserved):
                                    page['state'] = 'reading'
                                    page.pop('progress', None)
                                    page['since'] = datetime.now().isoformat(timespec='seconds')
                                    data.setdefault('out', {})[str(page['n'])] = [run, page['since'], os.getpid()]
                                    start = (page['n'], need, reserved)
                    if start:
                        #(started once the page is marked as being read, and that's saved)
                        n, need, reserved = start
                        cancel = threading.Event()
                        running[pool.submit(_read_page, app, job_id, n, api_key, user_id, reserved, cancel)] = (n, need, time.monotonic(), cancel)
                        continue
                    if not running:
                        if blocked and not gone:
                            time.sleep(3)   # (the page from before still finishing: asked again shortly)
                            continue
                        break
                    done, _ = wait(list(running), timeout=min(5, max(limit / 4, 0.05)), return_when=FIRST_COMPLETED)
                    finished = [(running.pop(f)[0], f.result()) for f in done]
                    #a page over its time limit is stopped (its reading ends at its next step) and the scan
                    #goes on: it's marked with why, and the pages that didn't make it are listed at the end
                    for f in [f for f, v in running.items() if time.monotonic() - v[2] > limit]:
                        n, _need, began, cancel = running.pop(f)
                        cancel.set()
                        app.logger.warning('scan {} page {} ran over {:.0f} minutes and was stopped'.format(job_id, n, limit / 60))
                        finished.append((n, {'n': n, 'state': 'error', 'timed_out': True, 'error': PAGE_TOO_SLOW.format(int(round(limit / 60)))}))
                    for n, result in finished:
                        if result is None:
                            continue
                        with page_lock(job_id) as data:
                            if data is None:
                                continue
                            out = data.get('out') or {}
                            if (out.get(str(n)) or [None])[0] == run:
                                out.pop(str(n), None)
                            #(only this reading's own answers: one that comes back after Pause, Save, Discard
                            #or a new reading is thrown away, the owner 2026-10-24, CA10c; a page saved
                            #meanwhile is never written over)
                            #(a page stopped on its own, Stop this page: what comes back for it is thrown away, the
                            #owner 2026-10-25, CK2)
                            if n in (data.get('stopped') or []):
                                pass
                            elif data.get('run') == run and data['pages'][n - 1].get('state') != 'saved':
                                if data['pages'][n - 1].get('spread'):
                                    result['spread'] = True  # (from a photo of two pages: kept through the reading)
                                #(joined to the page before while not read yet: kept through the reading; the owner, 2026-10-26)
                                if data['pages'][n - 1].get('join_prev'):
                                    result['join_prev'] = True
                                #(a page that didn't finish keeps what was paid for: its reading and the numbers
                                #picked so far, so reading it again goes on from there; CX1, the owner 2026-10-25)
                                if result.get('state') in ('error', 'waiting'):
                                    for k in ('qs_reading', 'numbers_so_far', 'numbers_done'):
                                        if k in data['pages'][n - 1] and k not in result:
                                            result[k] = data['pages'][n - 1][k]
                                data['pages'][n - 1] = result
                        stop = stop or bool(result.get('stop'))
            if gone:
                return
            with page_lock(job_id) as data:
                if data is None:
                    return
                job = db.session.get(ScanJob, job_id)
                job.status = 'ready'
                if data.get('pausing'):
                    #Pause: the pages being read were finished; the rest wait for Resume
                    _paused(data)
                    return
                data.pop('pausing', None)
                #(the hourly limit stops the rest until the teacher asks again; _tell_done only
                #tells when every page has been read)
                job.data = json.dumps(data)
                _tell_done(job)

        except Exception as exc:
            db.session.rollback()
            app.logger.exception('reading scan {} failed: {}'.format(job_id, exc))
            job = db.session.get(ScanJob, job_id)
            if job is not None:
                data = get_data(job)
                for p in data['pages']:
                    if p['state'] in ('waiting', 'reading'):
                        p.update(state='error', error='Something went wrong while reading this page. Press \u201cRead this page\u201d to read it again.')
                #(no page is still out with the AI after this, so reading one again starts at once; and a workbook
                #moved to the Trash meanwhile stays there: the code critic, 2026-10-25)
                data.pop('out', None)
                put_data(job, data)
                if job.status == 'reading':
                    job.status = 'ready'
                db.session.commit()
        finally:
            db.session.remove()


def _tell_done(job):
    """A notice for the teacher when a scan has been read all the way (not when it was canceled
    or stopped at the hourly limit) (the owner, 2026-10-18)."""
    from app.messages.models import notify
    pages = [p for p in get_data(job).get('pages') or [] if p.get('state') != 'saved']
    if not pages or any(p.get('state') in ('waiting', 'reading') for p in pages):
        return
    done = sum(1 for p in pages if p.get('state') == 'done')
    failed = len(pages) - done
    if not failed:
        body = 'Your workbook “{}” has been read and is ready to check.'.format(job.name)
    elif done:
        slow = sum(1 for p in pages if p.get('timed_out'))
        body = 'Your workbook “{}” has been read: {} of {} pages are ready to check; {} didn’t make it{}.'.format(
            job.name, done, len(pages), failed, ' ({} took too long)'.format(slow) if slow else '')
    else:
        body = 'Your workbook “{}” couldn’t be read. Open it and press “Read this page”.'.format(job.name)
    notify(job.author_id, body, '/quiz/scan/{}'.format(job.id))


PAUSED_NOTE = 'Stopped before this page was read.'  # (Stop, at once: the owner, 2026-10-27; it was Pause)


def still_out(data, run=None, limit=None):
    """The pages still out with the AI from another reading (stopped by Pause, but still finishing
    its step): {n}. A mark older than the page time limit and a few minutes is from a reading cut
    off by a restart, and doesn't count (the owner, 2026-10-24, CA10a)."""
    limit = limit if limit is not None else page_minutes() * 60
    old = datetime.now() - timedelta(seconds=limit + 300)
    away = set()
    for k, mark in list((data.get('out') or {}).items()):
        r, since = mark[0], mark[1]
        #(a reading whose server process is gone, e.g. the site restarted, isn't out any more: its mark
        #held the page back for many minutes, and nothing read it, 2026-10-25)
        try:
            fresh = datetime.fromisoformat(since) > old and len(mark) > 2 and _alive(mark[2])
        except (TypeError, ValueError):
            fresh = False
        if not fresh:
            data['out'].pop(k, None)
        elif r != run:
            away.add(int(k))
    return away


#about how many tokens each step's answer runs to (the sandbox's scans, 2026-10-25): a page's progress is how much of
#that has come back so far
STEP_TOKENS = {'photo': 160, 'reading': 6000, 'numbers': 4400, 'places': 2000}
#(the words beside a page's bar: the owner, 2026-10-25)
STEP_WORDS = {'photo': 'Checking the photo', 'reading': 'Reading the page', 'numbers': 'Picking the numbers', 'places': 'Finding the answer boxes'}


class Progress:
    """How far a page being read has got (the owner, 2026-10-25, CI1/CI2): its step, and about what percent of
    that step's answer has come back, kept in the page's draft (now and then, not on every bit) for the page's bar."""

    def __init__(self, job_id, n):
        self.job_id, self.n, self.last, self.shown = job_id, n, 0, None

    def step(self, name, pct=None):
        now = (name, pct)
        if now == self.shown:
            return
        #(a new percent of the same step at most every 5 seconds: each is a write of the whole workbook's draft,
        #and the page asks every 3; the code critic, 2026-10-25)
        if pct is not None and self.shown and self.shown[0] == name and time.monotonic() - self.last < 5:
            return
        self.shown, self.last = now, time.monotonic()
        try:
            with page_lock(self.job_id) as data:
                if data is not None and self.n <= len(data['pages']) and data['pages'][self.n - 1].get('state') == 'reading':
                    data['pages'][self.n - 1]['progress'] = {'step': name, 'pct': pct}
        except Exception:
            db.session.rollback()

    def counter(self, name):
        """on_progress for a streamed answer: tokens so far -> percent of the step (never 100 until it's done)."""
        return lambda got: self.step(name, min(95, int(100 * got / STEP_TOKENS[name])))


def _alive(pid):
    """Whether the server process that sent a page to the AI is still running."""
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


def mark_saved(job_id, data, ns, made):
    """After a page's Generate (the owner, 2026-10-25): the pages made into the quiz (ns, the first
    one leading) stay in the workbook as short "Generated" lines, so no page is numbered again under
    a reading; the edits on the other pages are kept, and the pages being read are left to their
    reading. made: save_all's answer. Returns how many pages are left to do."""
    quiz = (made.get('quizzes') or [None])[0]
    with page_lock(job_id) as fresh:
        if fresh is None:
            return 0
        for k, v in data.items():
            #(nor what the reading, Stop this page or the Trash changed since the page was loaded: the code critic, 2026-10-25)
            if k not in ('pages', 'run', 'dropped_run', 'paused', 'pausing', 'reading_since', 'out', '_plan',
                         'stopped', 'only', 'trashed_at', 'trashed_by', 'put_away'):
                fresh[k] = v
        for i, p in enumerate(data.get('pages') or []):
            if i >= len(fresh['pages']):
                break
            if p['n'] in ns:
                fresh['pages'][i] = {'n': p['n'], 'state': 'saved', 'kind': p.get('kind'),
                                     'made': {'quiz': quiz.id, 'title': quiz.title, 'problems': made.get('problems', 0)}
                                     if quiz is not None and p['n'] == ns[0] else {'with': ns[0]}}
            elif p.get('state') == 'done' and fresh['pages'][i].get('state') == 'done':
                p.pop('save', None)
                fresh['pages'][i] = p
        #(the page after it can't be joined to a page that's made already)
        after = next((p for p in fresh['pages'] if p['n'] == ns[-1] + 1), None)
        if after is not None:
            after['join_prev'] = False
        return sum(1 for p in fresh['pages'] if p.get('state') != 'saved')


def arrange_pages(job, data, order):
    """The pages in the order dragged on the workbook's thumbnails (the owner, 2026-10-25): numbered
    1, 2... again in that order, their files too. A page whose neighbor before it changed isn't
    joined to it any more. order: page numbers, every one once."""
    pages = data.get('pages') or []
    by_n = {p['n']: p for p in pages}
    if sorted(order) != sorted(by_n) or order == [p['n'] for p in pages]:
        return False
    before = {p['n']: (pages[k - 1]['n'] if k else None) for k, p in enumerate(pages)}
    new = [by_n[n] for n in order]
    for k, p in enumerate(new):
        if (new[k - 1]['n'] if k else None) != before[p['n']]:
            p['join_prev'] = False
    moved = {n: k for k, n in enumerate(order, 1)}
    _renumber_pages(job, new)
    for p in new:
        if (p.get('made') or {}).get('with') in moved:
            p['made']['with'] = moved[p['made']['with']]
    data['pages'] = new
    return True


def _paused(data):
    """The reading stopped by Pause: the pages not read yet wait, with a note, for Resume. The
    page being read is dropped (its reading still finishing is thrown away: dropped_run), and
    read again on Resume (the owner, 2026-10-22)."""
    if data.get('run'):
        data['dropped_run'] = data['run']
    data['run'] = None
    data.pop('pausing', None)
    data['paused'] = True
    for p in data['pages']:
        if p['state'] in ('waiting', 'reading'):
            p.update(state='waiting', error=PAUSED_NOTE)
            p.pop('progress', None)


STOPPED_NOTE = 'Stopped before this page was read.'


class ScanStopped(Exception):
    """A page's reading stopped while an answer was coming in (Stop, Stop this page, Move to Trash)."""


def stop_page(job, n):
    """Stop this page (the owner, 2026-10-25, CK2): one page being read is stopped at its next step and goes
    back to not read yet; what it cost so far is lost, and the other pages go on."""
    with page_lock(job.id) as data:
        if data is None or not 1 <= n <= len(data['pages']) or data['pages'][n - 1].get('state') != 'reading':
            return False
        data.setdefault('stopped', []).append(n)
        page = data['pages'][n - 1]
        page.update(state='waiting', error=STOPPED_NOTE)
        page.pop('progress', None)
        return True


def pause_reading(job, reading, now=False):
    """Pause (the owner, 2026-10-19; it was Cancel). A true pause (the owner, 2026-10-25, CH4): the pages
    already with the AI finish and are kept, they're paid for; no more start, and Resume goes on with
    the rest. (From 2026-10-22 it stopped them at once and threw their answers away, paid for again
    on Resume.) now: stop at once all the same, for Move to Trash."""
    with page_lock(job.id) as data:
        if data is None:
            return
        if reading and not now:
            data['pausing'] = True
            return
        _paused(data)
        job.status = 'ready'


def find_places_again(job_id, page):
    """Find the answer places on a page that was read again, without the AI (the owner, 2026-10-21:
    "Find the boxes again", e.g. after the finder was made better): its boxes are put where the
    finder puts them now; boxes moved by hand on it go back. False when the page has nothing to place."""
    from PIL import Image
    from . import pagelayout
    if page.get('state') != 'done' or page.get('kind') != 'problems' or not page.get('qs') \
            or not os.path.exists(page_file(job_id, page['n'])):
        return False
    flat = Image.open(page_file(job_id, page['n'])).convert('RGB')
    covered = {item['qs_id'] for item in page.get('items') or [] if item.get('qs_id') and item.get('values') and item.get('page_text')}
    page['slots'] = guess_places(page['qs'], pagelayout.find_slots(flat, {'problems': page['qs'], 'pictures': []}, covered), covered)
    return True


def keep_corrections(job, data):
    """The answer boxes a teacher moved or placed by hand, kept with their page (the owner,
    2026-10-22: every box fixed by hand becomes a test of the box finder). For each read page with
    one: SCAN_DIR/corrections/<scan>-p<page>-<time>/ page.jpg (the page as the finder saw it) and
    page.json (QuizScan's problems, and where every answer box ended up: 'truth', with 'by_hand'
    naming the ones the teacher moved). tools/scancorpus/build.py takes them in. Private like the
    scans; never fails a save."""
    try:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        for page in data.get('pages') or []:
            slots = page.get('slots') if isinstance(page.get('slots'), dict) else {}
            if page.get('state') != 'done' or not any(s.get('by_hand') for s in slots.values()):
                continue
            src = page_file(job.id, page['n'])
            if not os.path.exists(src):
                continue
            out = os.path.join(scan_root(), 'corrections', '{}-p{}-{}'.format(int(job.id), int(page['n']), stamp))
            os.makedirs(out, exist_ok=True)
            shutil.copyfile(src, os.path.join(out, 'page.jpg'))
            covered = [it['qs_id'] for it in page.get('items') or [] if it.get('qs_id') and it.get('values') and it.get('page_text')]
            truth = {k: {'kind': s.get('kind'), 'answer': s.get('answer')} for k, s in slots.items() if s.get('kind') == 'field' and s.get('answer')}
            with open(os.path.join(out, 'page.json'), 'w') as f:
                json.dump({'problems': page.get('qs') or [], 'pictures': [], 'covered': covered, 'truth': truth,
                           'by_hand': sorted(k for k, s in slots.items() if s.get('by_hand')),
                           'source': 'scan {} “{}” page {}, boxes fixed by hand {}'.format(job.id, data.get('name') or job.name, page['n'], stamp)}, f, indent=1)
    except Exception as exc:
        current_app.logger.warning('could not keep the box corrections of scan {}: {}'.format(job.id, exc))


def _renumber_pages(job, left):
    """The pages in `left` numbered 1, 2... again, their files too (a page 3 that becomes 1 never overwrites page 1
    first); pictures' "item:N" / "quiz:N" uses follow."""
    new = {p['n']: k for k, p in enumerate(left, 1)}
    #(files moved by way of a temporary name, so page 3 becoming 1 never overwrites page 1 first)
    for name in ('page', 'full', 'orig', 'thumb'):
        for old, k in new.items():
            src = os.path.join(job_dir(job.id), '{}-{}.jpg'.format(name, old))
            if os.path.exists(src):
                os.replace(src, src + '.moving-{}'.format(k))
        for old, k in new.items():
            src = os.path.join(job_dir(job.id), '{}-{}.jpg.moving-{}'.format(name, old, k))
            if os.path.exists(src):
                dst = os.path.join(job_dir(job.id), '{}-{}.jpg'.format(name, k))
                os.replace(src, dst)
                #(dated now, so a browser asks for it again instead of showing the page that had this number:
                #pages dragged into a new order looked as if they'd snapped back, the owner 2026-10-25)
                os.utime(dst)
    for name in os.listdir(job_dir(job.id)):
        m = re.match(r'^(page|full|orig|thumb)-(\d+)\.jpg$', name)
        if m and int(m.group(2)) > len(left):
            os.remove(os.path.join(job_dir(job.id), name))
    def renumbered(use):
        m = re.match(r'^(item|quiz):(\d+)(:.*)?$', use or '')
        if not m:
            return use
        return '{}:{}{}'.format(m.group(1), new[int(m.group(2))], m.group(3) or '') if int(m.group(2)) in new else ''
    for k, page in enumerate(left, 1):
        page['n'] = k
        for pic in page.get('pictures') or []:
            pic['use'] = renumbered(pic.get('use'))


def keep_leftovers(job, data):
    """After Save (the owner, 2026-10-22: save page by page): the pages not saved (kept back,
    not read yet, or that couldn't be read) stay as a smaller scan of their own, stashed under
    the same name, numbered 1, 2... again (their files too). Returns how many are left; with
    none, the caller removes the scan as before."""
    left = [p for p in data.get('pages') or [] if p.get('state') != 'saved' and not (p.get('state') == 'done' and p.get('save') is not False)]
    if not left:
        return 0
    _renumber_pages(job, left)
    for page in left:
        page['save'] = True
    #(the first one left can't be joined to a page that was saved)
    for page in left:
        if page.get('state') == 'done' and page.get('kind') == 'problems':
            page['join_prev'] = False
            break
    data['pages'] = left
    data['put_away'] = datetime.now().isoformat(timespec='seconds')
    data['kept_at'] = data['put_away']
    data.pop('_plan', None)
    job.pages = len(left)
    put_data(job, data)
    return len(left)


def drop_page(job, data, n):
    """Discard one page that didn't make it through (the owner, 2026-10-23): it leaves the scan, with its
    files, and the pages after it are numbered on again. Returns how many pages are left (0: the caller removes the scan)."""
    left = [p for p in data.get('pages') or [] if p['n'] != int(n)]
    if len(left) == len(data.get('pages') or []):
        return len(left)
    if not left:
        return 0
    #(the page after it isn't joined to the one before it by accident: a join was with the page taken out)
    after = next((p for p in left if p['n'] == int(n) + 1), None)
    if after is not None:
        after.pop('join_prev', None)
    _renumber_pages(job, left)
    data['pages'] = left
    data.pop('_plan', None)
    job.pages = len(left)
    put_data(job, data)
    return len(left)


def helper_hints(job, data, urls):
    """What the Helper on a workbook page says (the owner, 2026-10-25, CL2: page by page): one line for each page
    that isn't ready (not read yet, didn't make it, problems to fix, answer boxes to place, its quiz's title), then
    what's wrong with the workbook as a whole; with nothing wrong, how many quizzes can be made. It only reads
    the page: the choices are on each page's own card (the owner, 2026-10-24). urls: kept for the callers."""
    from . import services as S
    hints = []
    pages = data.get('pages') or []
    gaps = {}
    for g in missing_places(data):
        gaps.setdefault(g[0], []).append(g[2])
    leads = lead_of(data)
    seen = {}
    #(each page that isn't ready says what to do next, as numbered steps; a page ready to make says so: the owner,
    #2026-10-25, "more helpful about what steps need to be taken instead of just throwing a bunch of problems at me")
    gen = 'Press \u201cGenerate quiz\u201d.'
    #(the pages being read now, as one gray line first, so the Helper isn't blank while a workbook is read: the owner, 2026-10-25)
    now = [p['n'] for p in pages if p.get('state') == 'reading']
    #(the workbook being read, as the page decides it (scan_routes._reading): its buttons wait till then)
    reading_now = bool(now) or (getattr(job, 'status', None) == 'reading' and job.updated_at and job.updated_at > datetime.now() - STALE)
    if now:
        names = str(now[0]) if len(now) == 1 else '{} and {}'.format(', '.join(map(str, now[:-1])), now[-1])
        hints.append({'level': 'tip', 'key': 'reading', 'text': 'Page{} {} {} being read\u2026'.format(
            '' if len(now) == 1 else 's', names, 'is' if len(now) == 1 else 'are')})
    #(step 3 of the workbook page, once every page is read, two or more not made yet: the owner, 2026-10-27, "the Helper should
    #be telling me what to do for step 3")
    if not reading_now and sum(1 for p in pages if p.get('state') != 'saved') > 1:
        hints.append({'level': 'tip', 'key': 'step-3', 'text': 'Step 3: put the pages in order and join any that make one quiz. '
                      'Then press \u201cGenerate quiz\u201d on each.'})
    for p in pages:
        n, state = p['n'], p.get('state')
        #(nothing more about a page being read or made already: its card shows how it's going)
        if state in ('saved', 'reading'):
            continue
        if state == 'waiting':
            #(gray, like the quiz Helper's tips: nothing to fix, it's waiting for its turn or for Resume)
            #(with its next step: the code critic and the user critic, 2026-10-25)
            hints.append({'level': 'tip', 'key': 'page-{}'.format(n), 'text': 'Page {} hasn\u2019t been read yet.{}'.format(
                n, '' if reading_now else ' Press \u201cResume all\u201d.')})
            continue
        if state != 'done':
            why = 'the AI\u2019s answer ran too long' if p.get('timed_out') or 'too long' in (p.get('error') or '') else None
            text = 'Page {} didn\u2019t make it ({})'.format(n, why) if why else \
                'Page {} didn\u2019t make it: {}'.format(n, shown_error(p.get('error')) or 'it couldn\u2019t be read.')
            steps = ['Press \u201cRead this page\u201d to finish it (a few AI calls), or \u201cUse what was read\u201d to finish it by hand.'] \
                if p.get('qs_reading') else ['Press \u201cRead this page\u201d to read it again (a few AI calls).']
            #(those buttons are drawn once reading ends: the user critic, 2026-10-25)
            if reading_now:
                steps = ['Wait until every page has been read, then press \u201cRead this page\u201d.']
            hints.append({'level': 'error', 'key': 'page-{}'.format(n), 'text': text, 'steps': steps})
            continue
        bad = [e for e in (checked_item(it)['errors'] for it in p.get('items') or [] if it.get('include')) if e]
        heads, steps = [], []
        if gaps.get(n):
            k = len(gaps[n])
            heads.append('{} answer box{} to place'.format(k, '' if k == 1 else 'es'))
            steps += ['Press \u201cPlace the answer boxes again (free)\u201d under the page picture.',
                      'Drag any dashed box that\u2019s off onto where its answer goes.']
        if bad:
            heads.append('{} problem{} to fix (marked !)'.format(len(bad), '' if len(bad) == 1 else 's'))
            steps.append('Open each one and correct it.')
        lead = leads.get(n) == n and p.get('kind') == 'problems'
        if lead:
            title = ' '.join((p.get('title') or '').split())
            if not title:
                heads.append('no quiz title')
                steps.append('Give its quiz a title.')
            elif S.quiz_name_taken(title) or title.lower() in seen:
                heads.append('a quiz is already called \u201c{}\u201d'.format(title))
                steps.append('Give its quiz a different title.')
            seen[title.lower()] = n
        if heads:
            if lead:
                steps.append(gen)
            #(red, like the quiz Helper's: each of these keeps "Generate quiz" from working until it's done; the owner, 2026-10-25)
            hints.append({'level': 'error', 'key': 'page-{}'.format(n),
                          'text': 'Page {}: {}'.format(n, '; '.join(heads)), 'steps': steps})
        elif lead:
            #(pages joined into one quiz are named together, its Generate being on the first: the owner, 2026-10-25)
            grp = sorted(k for k, v in leads.items() if v == n)
            if len(grp) > 1:
                names = '{} and {}'.format(', '.join(map(str, grp[:-1])), grp[-1])
                text = 'Pages {} are joined and ready: press \u201cGenerate quiz\u201d on page {}.'.format(names, n)
            else:
                text = 'Page {} is ready: press \u201cGenerate quiz\u201d.'.format(n)
            hints.append({'level': 'ok', 'key': 'page-{}'.format(n), 'text': text})
    if data.get('folder'):
        err = S.new_subject_name_error('problems', data['folder'])
        if err:
            hints.append({'level': 'error', 'text': err})
    return hints


def put_away(job, away=True):
    """Put away (the owner, 2026-10-20): a paused scan or a draft moved out of Current scans (and
    the Dashboard's Scanner) into Scan workbook pages' Put away card, as it is, until it's taken
    out, resumed or discarded. away=False takes it out again."""
    with page_lock(job.id) as data:
        if data is None:
            return
        if away:
            data['put_away'] = datetime.now().isoformat(timespec='seconds')
        else:
            data.pop('put_away', None)


def scan_kind(data, reading):
    """Which of the five a scan is (the owner, 2026-10-19): 'reading'; 'stopped' (a page couldn't
    be read); 'paused' (pages waiting: Pause, or the hourly limit); 'draft' (Keep draft pressed);
    'ready' (read all the way, waiting to be checked)."""
    pages = data.get('pages') or []
    if reading:
        return 'reading'
    if any(p.get('state') == 'error' for p in pages):
        return 'stopped'
    if any(p.get('state') in ('waiting', 'reading') for p in pages):
        return 'paused'
    if data.get('kept_at'):
        return 'draft'
    return 'ready'


QS_CALLS = 2   # AI calls QuizScan may make on a page: the photo check (photos only), then the reading


class _Logged:
    """The Claude client QuizScan is given (the owner, 2026-10-20): each call it makes is logged as
    its own AI call, with its tokens, like the other AI buttons (a photo makes two: the photo
    check, then the reading)."""

    def __init__(self, client, job, n, user_id, cancel=None, progress=None):
        self._client, self._job, self._n, self._user_id, self._cancel = client, job, n, user_id, cancel
        self._progress = progress
        self.messages = self

    def stream(self, **request):
        #(Pause or Discard meanwhile: no more AI calls for this page, the owner 2026-10-24, CA10b)
        if self._cancel is not None and self._cancel.is_set():
            import quizscan
            raise quizscan.QuizScanError('Stopped.')
        try:
            ask = request['messages'][-1]['content'][-1]['text']
        except (KeyError, IndexError, TypeError):
            ask = ''
        what = 'reading' if 'page format' in ask else 'photo check'
        call = AICall(user_id=self._user_id, created=datetime.now(), kind='scan',
                      request='Scan {} page {}: {}'.format(self._job, self._n, what), ok=False)
        on = None
        if self._progress is not None:
            name = 'reading' if what == 'reading' else 'photo'
            self._progress.step(name, 0)
            on = self._progress.counter(name)
        try:
            return _LoggedStream(self._client.messages.stream(**request), call, on, self._cancel)
        except Exception:
            _log_call(call)
            raise


class _LoggedStream:
    def __init__(self, manager, call, on_progress=None, cancel=None):
        self._manager, self._call, self._running, self._on, self._cancel = manager, call, None, on_progress, cancel

    def __enter__(self):
        try:
            self._running = self._manager.__enter__()
        except Exception:
            _log_call(self._call)
            raise
        return self

    def get_final_message(self):
        from .ai_helper import streamed

        #(Stop, Stop this page or Move to Trash while the answer comes in: it's hung up on at once, so the AI stops
        #working, and costing, right there; it used to run to its end and be thrown away; the owner, 2026-10-27)
        def tick(n):
            if self._cancel is not None and self._cancel.is_set():
                import quizscan
                raise quizscan.QuizScanError('Stopped.')
            if self._on is not None:
                self._on(n)
        msg = streamed(self._running, tick)
        usage = getattr(msg, 'usage', None)
        self._call.ok = True
        self._call.input_tokens = getattr(usage, 'input_tokens', None)
        self._call.output_tokens = getattr(usage, 'output_tokens', None)
        return msg

    def __exit__(self, *exc):
        try:
            return self._manager.__exit__(*exc)
        finally:
            _log_call(self._call)

    def __getattr__(self, name):
        return getattr(self._running, name)


def _log_call(call):
    db.session.add(call)
    db.session.commit()


def _quizscan_client(api_key):
    """QuizScan's own Claude client (its longer wait suits a dense page)."""
    from quizscan.reader import make_client
    return make_client(api_key)


def ai_room(user_id, need, reserved=0):
    """Whether need more AI calls fit in the hourly limit, with reserved calls still to come
    from pages being read beside this one."""
    from app import tuning
    since = datetime.now() - timedelta(hours=1)
    return AICall.query.filter(AICall.user_id == user_id, AICall.created >= since).count() + reserved + need <= tuning.get('ai_hourly')


#a busy page's random numbers are picked this many problems at a time, each group kept as soon as it's back, so
#the AI's answer never runs too long and a page stopped partway goes on from the next group (the owner, 2026-10-25, CX1)
NUMBERS_GROUP = 15


def number_groups(qs, done=()):
    """The groups of problem ids (as text) still to get their numbers, in page order."""
    ids = [str(p.get('id')) for p in (qs or {}).get('problems') or [] if p.get('type') != 'paper']
    groups = [ids[i:i + NUMBERS_GROUP] for i in range(0, len(ids), NUMBERS_GROUP)]
    return [g for g in groups if not set(g) <= set(done)]


def calls_for(page):
    """The AI calls a waiting page needs before its places are checked: QuizScan's (unless its
    reading is kept from before) and the numbers (a call for each group still to do)."""
    page = page or {}
    qs = page.get('qs_reading')
    if qs is None:
        return QS_CALLS + 1
    return max(1, len(number_groups(qs, page.get('numbers_done') or ())))


def read_one(job, n, api_key, user_id, reserved=0, cancel=None):
    """Read page n: QuizScan reads the page (exactly, and where everything is), then the AI
    gives its problems random numbers, then the page picture is leveled and searched for the
    places students answer (pagelayout.py), then the AI checks those places (check_places).
    Two to six AI calls, all counted against the hourly limit. reserved: calls still to come
    from the pages being read beside this one.
    Returns the page's draft, or {'state': 'error', ...} (the owner, 2026-10-18)."""
    from app import tuning
    from . import ai_helper, pagelayout
    hourly = tuning.get('ai_hourly')
    #(how long each step takes goes in the log, and a page over its time limit stops at its next step: the owner, 2026-10-23)
    began = [time.monotonic(), time.monotonic()]

    def step(name):
        now = time.monotonic()
        current_app.logger.info('scan {} page {}: {} took {:.1f}s ({:.1f}s in all)'.format(job.id, n, name, now - began[1], now - began[0]))
        began[1] = now
        return cancel is not None and cancel.is_set()

    stopped = {'n': n, 'state': 'error', 'timed_out': True, 'error': PAGE_TOO_SLOW.format(int(round(page_minutes())))}
    progress = Progress(job.id, n)
    #(read before, and only the numbers failed: QuizScan's reading is kept, so it isn't paid for twice)
    kept = get_data(job)['pages'][n - 1] or {}
    qs = kept.get('qs_reading')
    if not ai_room(user_id, calls_for(kept), reserved):
        return {'n': n, 'state': 'waiting', 'stop': True,
                'error': 'You’ve used the AI helper {} times in the last hour, so this page is waiting. '
                         'Press “Read this page” on it in a while.'.format(hourly)}
    try:
        import quizscan
    except ImportError:
        return {'n': n, 'state': 'error', 'error': 'The page reader (QuizScan) isn’t installed on this site.'}
    path = page_file(job.id, n)
    if qs is None:
        #(QuizScan reads the full-size page as uploaded, so a photo is straightened and its pictures
        #found at full detail; it's kept as it was (orig_file), as the full-size page becomes the
        #straightened one. A scan from before full-size pages has only its smaller one)
        if not os.path.exists(orig_file(job.id, n)) and os.path.exists(full_file(job.id, n)):
            os.replace(full_file(job.id, n), orig_file(job.id, n))
        src = orig_file(job.id, n) if os.path.exists(orig_file(job.id, n)) else path
        #(read again with the teacher's words on what was wrong: the owner, 2026-10-20)
        note = (get_data(job)['pages'][n - 1] or {}).get('note')
        try:
            qs = quizscan.convert_image(src, model=tuning.get('scan_model'),
                                        client=_Logged(_quizscan_client(api_key), job.id, n, user_id, cancel, progress),
                                        **({'note': note} if note else {}))[0]
        except quizscan.QuizScanError as exc:
            return {'n': n, 'state': 'error', 'error': str(exc)}
        if step('QuizScan reading'):
            return stopped
        #the page as QuizScan read it: flattened and leveled, so every box is a place on it; then
        #made truly level (its rows straight across, its margins straight down, the paper's dark
        #edge painted out) and QuizScan's boxes laid on its own printed lines (the owner, 2026-10-20).
        #Measured on the smaller page (where the places are found, and quick), and the full-size
        #page made level the same way, for cutting pictures from (the owner, 2026-10-20)
        full = quizscan.flat_page(src, qs).convert('RGB')
        small = full.copy()
        small.thumbnail((long_side(), long_side()))
        small, qs, full = pagelayout.level_page(small, qs, full=full)
        qs = pagelayout.snap_boxes(small, qs)
        if step('flattening and leveling the page'):
            return stopped
        qs['size'] = {'width': small.size[0], 'height': small.size[1]}
        full.save(full_file(job.id, n), 'JPEG', quality=90)
        small.save(path, 'JPEG', quality=90)
        #(kept at once, so a reading cut off from here on, e.g. by the site restarting, doesn't pay
        #for QuizScan again: the owner, 2026-10-18)
        with page_lock(job.id) as data:
            if data is not None:
                data['pages'][n - 1]['qs_reading'] = qs
    from PIL import Image
    if cancel is not None and cancel.is_set():
        return stopped
    flat = Image.open(path).convert('RGB')
    #the numbers, a group of problems at a time; each group's kept as soon as it's back (CX1): reading the page again
    #after a stop, a pause or a failure asks only for the groups not done yet
    numbers = dict((get_data(job)['pages'][n - 1] or {}).get('numbers_so_far') or {})
    done = list((get_data(job)['pages'][n - 1] or {}).get('numbers_done') or [])
    todo = number_groups(qs, done)
    whole = sum(len(g) for g in number_groups(qs)) or 1
    progress.step('numbers', int(100 * len(done) / whole))
    for group in todo:
        call = AICall(user_id=user_id, created=datetime.now(), kind='scan', request='Scan {} page {}: numbers'.format(job.id, n), ok=False)
        base = len(done)
        try:
            share = STEP_TOKENS['numbers'] * len(group) / whole
            def numbers_tick(t, base=base, size=len(group)):
                #(hung up on at once when stopped, as the reading is: the owner, 2026-10-27)
                if cancel is not None and cancel.is_set():
                    raise ScanStopped()
                progress.step('numbers', min(95, int(100 * (base + size * min(1, t / share)) / whole)))
            got, usage = ai_helper.page_numbers(api_key, qs, ids=set(group), on_progress=numbers_tick)
            call.ok = True
            call.input_tokens, call.output_tokens = usage['input_tokens'], usage['output_tokens']
        except ScanStopped:
            return stopped
        except ai_helper.AITooLong:
            #(not the description box's "Please shorten it": a way forward for this page: the owner, 2026-10-21)
            return {'n': n, 'state': 'error', 'error': PAGE_TOO_LONG, 'qs_reading': qs, 'numbers_so_far': numbers, 'numbers_done': done}
        except ai_helper.AIError as exc:
            return {'n': n, 'state': 'error', 'error': str(exc), 'qs_reading': qs, 'numbers_so_far': numbers, 'numbers_done': done}
        finally:
            db.session.add(call)
            db.session.commit()
            current_app.logger.info('scan {} page {} numbers for {} problems (ok={}, tokens in/out {}/{})'.format(
                job.id, n, len(group), call.ok, call.input_tokens, call.output_tokens))
        numbers.update(got)
        done.extend(group)
        with page_lock(job.id) as data:
            if data is not None and n <= len(data['pages']):
                data['pages'][n - 1]['numbers_so_far'] = numbers
                data['pages'][n - 1]['numbers_done'] = done
        if step('the AI\u2019s numbers ({} of {})'.format(len(done), whole)):
            return stopped
    return finish_page(job, n, qs, numbers, flat, api_key, user_id, progress=progress, step=step, stopped=stopped)


def finish_page(job, n, qs, numbers, flat, api_key=None, user_id=None, progress=None, step=None, stopped=None):
    """The rest of reading a page, once it's read and has its numbers: its answer places found on the picture,
    checked by the AI (only with api_key), the font picked, and its draft made. Without api_key, no AI call:
    "Use what was read" on a page that stopped partway (the owner, 2026-10-25, CX4); its problems with no
    numbers yet keep the page's own."""
    from . import pagelayout
    step = step or (lambda name: False)
    if progress:
        progress.step('places')
    covered = {pid for pid, item in numbers.items() if item.get('values') and item.get('page_text')}
    slots = guess_places(qs.get('problems') or [], pagelayout.find_slots(flat, qs, covered), covered)
    if step('finding the answer places'):
        return stopped
    #(the AI looks at the page as a student will see it, and the places it moves are checked here)
    if api_key:
        slots, checked = check_places(job, n, flat, qs, slots, covered, api_key, user_id)
    else:
        checked = {'rounds': 0, 'moved': 0, 'error': None}
    if step('checking the answer places'):
        return stopped
    samples = {}
    for p in qs['problems']:
        if p['id'] in covered:
            samples[p['id']] = pagelayout.covered_words(p['text'], p.get('number') or '')
    font = pagelayout.pick_font(flat, qs, slots, samples, os.path.join(current_app.static_folder, 'fonts'))
    step('choosing the font')
    page = draft_page(n, quizscan_raw(qs, numbers))
    page.update(size=qs['size'], slots=slots, font=font, checked=checked,
                qs=[{k: p.get(k) for k in ('id', 'type', 'box', 'choices', 'text', 'number')} for p in qs['problems']])
    return page


def guess_places(problems, slots, covered=()):
    """An answer box for each problem the finder couldn't place (no blank printed after it, e.g. "3/4 + 1/5 ="): just
    to the right of the problem, as tall as it, up to the next problem on its line or the page's edge, marked
    'guessed' (the owner, 2026-10-25: "box right after the =", dragged by hand where it's off). slots is changed
    in place and returned."""
    boxes = [q for q in problems if isinstance(q.get('box'), dict)]
    for q in boxes:
        if q['id'] in slots:
            continue
        b = q['box']
        #(the nearest problem to its right on the same line: the box stops short of it)
        stop = min([o['box']['left'] for o in boxes if o is not q and o['box']['left'] >= b['right'] - 0.005
                    and min(o['box']['bottom'], b['bottom']) - max(o['box']['top'], b['top']) > 0.3 * (b['bottom'] - b['top'])]
                   + [0.99])
        left = b['right'] + 0.005
        right = min(left + 0.10, stop - 0.008)
        if right - left < 0.03:
            continue
        h = b['bottom'] - b['top']
        slots[q['id']] = {'kind': 'field', 'answer': {'left': round(left, 4), 'top': b['top'], 'right': round(right, 4), 'bottom': b['bottom']},
                          'text': dict(b) if q['id'] in covered else None, 'char': round(min(0.03, 0.5 * h), 5), 'guessed': True}
    return slots


def use_reading(job, n):
    """Use what was read (the owner, 2026-10-25, CX4): a page that stopped after it was read becomes a normal page
    to fix and generate, with the numbers picked so far (the rest keep the page's own); no AI call. Returns True
    when it was made."""
    from PIL import Image
    page = (get_data(job)['pages'][n - 1] or {}) if 1 <= n <= len(get_data(job)['pages']) else {}
    qs = page.get('qs_reading')
    if qs is None or page.get('state') not in ('error', 'waiting') or not os.path.exists(page_file(job.id, n)):
        return False
    flat = Image.open(page_file(job.id, n)).convert('RGB')
    made = finish_page(job, n, qs, dict(page.get('numbers_so_far') or {}), flat)
    with page_lock(job.id) as data:
        if data is None or data['pages'][n - 1].get('state') not in ('error', 'waiting'):
            return False
        if data['pages'][n - 1].get('spread'):
            made['spread'] = True
        if data['pages'][n - 1].get('join_prev'):
            made['join_prev'] = True
        data['pages'][n - 1] = made
    return True


CHECK_ROUNDS = 3   # AI looks at a page's answer places at most this often (one check, two more if it moved some)


def _overlap(a, b):
    """The area two boxes share, as a fraction of the page."""
    w = min(a['right'], b['right']) - max(a['left'], b['left'])
    h = min(a['bottom'], b['bottom']) - max(a['top'], b['top'])
    return w * h if w > 0 and h > 0 else 0.0


def _area(b):
    return max(0.0, b['right'] - b['left']) * max(0.0, b['bottom'] - b['top'])


def _sane_box(box, most_h=0.08):
    """A box the AI gave, if it's a real place on the page: inside it, not a sliver, not huge."""
    if not isinstance(box, dict):
        return None
    try:
        l, t, r, b = (float(box[k]) for k in ('left', 'top', 'right', 'bottom'))
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= l < r <= 1 and 0 <= t < b <= 1) or r - l < 0.008 or b - t < 0.006 or b - t > most_h or r - l > 0.6:
        return None
    return {'left': round(l, 4), 'top': round(t, 4), 'right': round(r, 4), 'bottom': round(b, 4)}


def draw_places(img, qs, slots):
    """The page as the AI checks it: each answer place in blue and covered wording in green, each
    labeled with its problem's id; a problem with no place gets a red label at its line."""
    from PIL import ImageDraw
    pic = img.convert('RGB').copy()
    W, H = pic.size
    d = ImageDraw.Draw(pic)
    P = lambda b: (b['left'] * W, b['top'] * H, b['right'] * W, b['bottom'] * H)
    for p in qs.get('problems') or []:
        s = slots.get(p['id'])
        if s and s.get('kind') == 'field':
            d.rectangle(P(s['answer']), outline=(0, 70, 255), width=3)
            d.text((s['answer']['right'] * W + 3, s['answer']['top'] * H), p['id'], fill=(0, 70, 255))
            if s.get('text'):
                d.rectangle(P(s['text']), outline=(0, 160, 0), width=2)
                d.text((s['text']['left'] * W, s['text']['top'] * H - 11), p['id'], fill=(0, 160, 0))
        elif not s and isinstance(p.get('box'), dict) and p.get('type') not in ('paper', 'essay'):
            d.text((p['box']['right'] * W + 3, p['box']['top'] * H), p['id'] + ' ?', fill=(230, 0, 0))
    return pic


def check_places(job, n, img, qs, slots, covered, api_key, user_id, client=None):
    """The AI checks a read page's answer places (the owner, 2026-10-20): it looks at the page
    as a student will see it and says what to move; every move is checked here before it's
    taken (on the page, on the problem's own line, never over another problem's place, the
    wording never over the blank). At most CHECK_ROUNDS looks, each one AI call counted
    against the hourly limit; stops when it says all is well or a look changes nothing.
    Returns (slots, {'rounds': looks, 'moved': places changed, 'error': text or None})."""
    from app import tuning
    from . import ai_helper, pagelayout
    probs = {p['id']: p for p in qs.get('problems') or []
             if p.get('type') not in ('paper', 'essay', 'choice_one', 'choice_many', 'truefalse') and isinstance(p.get('box'), dict)}
    if not probs:
        return slots, {'rounds': 0, 'moved': 0, 'error': None}
    slots = {k: dict(v) for k, v in slots.items()}
    report = {'rounds': 0, 'moved': 0, 'error': None}
    chars = [s.get('char') for s in slots.values() if s.get('char')]
    char = sorted(chars)[len(chars) // 2] if chars else 0.015
    for rnd in range(1, CHECK_ROUNDS + 1):
        since = datetime.now() - timedelta(hours=1)
        if AICall.query.filter(AICall.user_id == user_id, AICall.created >= since).count() + 1 > tuning.get('ai_hourly'):
            break
        listing = []
        for pid, p in probs.items():
            s = slots.get(pid) if (slots.get(pid) or {}).get('kind') == 'field' else None
            listing.append({'id': pid, 'label': (p.get('number') or '').strip(), 'text': p.get('text') or '',
                            'changes': pid in covered, 'answer': s['answer'] if s else None,
                            'text_box': s.get('text') if s else None})
        buf = io.BytesIO()
        draw_places(img, qs, slots).save(buf, 'JPEG', quality=85)
        call = AICall(user_id=user_id, created=datetime.now(), kind='scan',
                      request='Scan {} page {}: check {}'.format(job.id, n, rnd), ok=False)
        try:
            answer, usage = ai_helper.check_places(api_key, buf.getvalue(), listing, client=client)
            call.ok = True
            call.input_tokens, call.output_tokens = usage['input_tokens'], usage['output_tokens']
        except ai_helper.AIError as exc:
            report['error'] = str(exc)
            break
        finally:
            db.session.add(call)
            db.session.commit()
        report['rounds'] = rnd
        moved = 0
        for fix in answer['fixes']:
            pid = str(fix.get('id'))
            p = probs.get(pid)
            if p is None:
                continue  # (an id that isn't on the list: never a new problem)
            line = p['box']
            lh = line['bottom'] - line['top']
            slot = dict(slots.get(pid) or {'kind': 'field', 'answer': None, 'text': None, 'char': char})
            if slot.get('kind') != 'field':
                continue
            ans = _sane_box(fix.get('answer'))
            if ans:
                mid = (ans['top'] + ans['bottom']) / 2
                own_line = line['top'] - 0.6 * lh <= mid <= line['bottom'] + 1.6 * lh
                others = [o['answer'] for k, o in slots.items() if k != pid and o.get('kind') == 'field' and o.get('answer')]
                words = [o['text'] for k, o in slots.items() if k != pid and o.get('text')]
                if own_line and not any(_overlap(ans, o) > 0 for o in others) and \
                        not any(_overlap(ans, o) > 0.2 * _area(ans) for o in words):
                    slot['answer'] = ans
                    moved += 1
            txt = _sane_box(fix.get('text')) if pid in covered else None
            if txt and slot.get('answer') and _overlap(txt, slot['answer']) <= 0.1 * _area(txt):
                mid = (txt['top'] + txt['bottom']) / 2
                if line['top'] - 0.6 * lh <= mid <= line['bottom'] + 0.6 * lh:
                    slot['text'] = txt
                    slot['paper'] = pagelayout.paper_color(img, txt)
                    moved += 1
            if slot.get('answer'):
                slots[pid] = slot
        report['moved'] += moved
        current_app.logger.info('scan {} page {} check {}: all good {}, {} fixes, {} taken'.format(
            job.id, n, rnd, answer['all_good'], len(answer['fixes']), moved))
        if answer['all_good'] or not moved:
            break
    return slots, report


def quizscan_raw(qs, numbers):
    """QuizScan's page and the AI's numbers -> the page in the form draft_page reads."""
    kind = {'quiz': 'problems', 'picture': 'picture'}.get(qs.get('page_kind'), 'other')
    raw = {'page_kind': kind, 'title': ' '.join((qs.get('title') or '').split()), 'directions': qs.get('directions'), 'notes': qs.get('notes'),
           'pictures': [{'id': p['id'], 'box': p['box'], 'label': p.get('label') or ''} for p in qs.get('pictures') or []
                        if kind != 'problems' or p.get('role') == 'question'],
           'items': []}
    for p in qs.get('problems') or []:
        #(nothing to ask: QuizScan can list an empty problem with no place on the page, which would
        #only stop Save with "Please write the question"; the owner, 2026-10-19)
        if not isinstance(p.get('box'), dict) and not (p.get('question') or p.get('text') or '').strip():
            continue
        pics = [x['id'] for x in p.get('pictures') or []]
        if p.get('type') == 'paper':
            question = '\n'.join(x for x in [p.get('directions'), p.get('question')] if x)
            raw['items'].append({'kind': 'paper_only', 'qs_id': p['id'], 'box': p['box'], 'picture_ids': pics, 'qtype': 'essay',
                                 'title': '{} {}'.format(qs.get('title') or 'Page', (p.get('number') or '').strip('.)( ')).strip(),
                                 'question': question, 'answer': p.get('answer') or '', 'values': [], 'page_question': question})
            continue
        item = numbers.get(p['id'])
        if item is None:
            #(the AI left it out: the page's own wording, numbers kept)
            choices = '\n'.join(('*' if c == p.get('answer') else '') + c for c in p.get('choices') or [])
            question = '\n'.join(x for x in [p.get('directions'), p.get('question')] if x)
            item = {'qtype': p.get('type'), 'title': '', 'question': question, 'answer': p.get('answer') or '',
                    'choices': choices, 'values': [], 'page_question': question, 'page_answer': p.get('answer') or '',
                    'page_choices': choices, 'page_text': None, 'fixed_reason': 'The AI didn’t return this one.'}
        raw['items'].append(dict(item, kind='question', qs_id=p['id'], box=p['box'], picture_ids=pics))
    return raw


def _num(v, default):
    try:
        return min(1.0, max(0.0, float(v)))
    except (TypeError, ValueError):
        return default


def clean_box(box, least=0.02):
    """{'left', 'top', 'right', 'bottom'} as fractions of the page, the right way round
    and at least a sliver big (least: a picture 2% of the page; an answer place on one printed
    line is thinner); the whole page when it can't be read."""
    if isinstance(box, str):
        parts = box.split(',')
        box = dict(zip(('left', 'top', 'right', 'bottom'), parts)) if len(parts) == 4 else {}
    box = box if isinstance(box, dict) else {}
    l, t = _num(box.get('left'), 0.0), _num(box.get('top'), 0.0)
    r, b = _num(box.get('right'), 1.0), _num(box.get('bottom'), 1.0)
    l, r = min(l, r), max(l, r)
    t, b = min(t, b), max(t, b)
    if r - l < least or b - t < least:
        return {'left': 0.0, 'top': 0.0, 'right': 1.0, 'bottom': 1.0}
    return {'left': round(l, 4), 'top': round(t, 4), 'right': round(r, 4), 'bottom': round(b, 4)}


def draft_page(n, raw):
    """The AI's reading of page n -> the draft the review page shows and edits."""
    from .ai_helper import clean
    kind = raw.get('page_kind') if raw.get('page_kind') in ('problems', 'picture', 'other') else 'other'
    page = {'n': n, 'state': 'done', 'kind': kind,
            'title': str(raw.get('title') or '').strip()[:64] or 'Page {}'.format(n),
            'directions': str(raw.get('directions') or '').strip(),
            'notes': str(raw.get('notes') or '').strip(),
            'join_prev': False, 'shuffle': False, 'calculator': False,
            'pictures': [], 'items': []}
    #a page with no questions (a cover, a picture page): just the whole page, one picture, saved in
    #Pictures; nothing cut out of it (the owner, 2026-10-19: a cover came back as 12 pieces)
    if kind != 'problems':
        page['pictures'] = [{'id': 'p1', 'box': clean_box(None), 'label': page['title'], 'keep': True, 'use': ''}]
        return page
    ids = {}
    for i, pic in enumerate(raw.get('pictures') or []):
        pid = 'p{}'.format(i + 1)
        ids[str(pic.get('id') or '')] = pid
        page['pictures'].append({'id': pid, 'box': clean_box(pic.get('box')), 'label': str(pic.get('label') or '')[:64],
                                 'keep': True, 'use': ''})
    for raw_item in raw.get('items') or []:
        i = len(page['items'])
        paper = raw_item.get('kind') == 'paper_only'
        fill = clean(raw_item, 'problem')
        item = {'include': True, 'kind': 'paper' if paper else 'question', 'box': clean_box(raw_item.get('box')),
                'qtype': 'paper' if paper else (fill['qtype'] if fill['qtype'] in QTYPES else 'numeric'),
                'title': fill['title'] or '{} {}'.format(page['title'], i + 1)[:64],
                'question': fill['question'], 'answer': fill['answer'], 'choices': fill['choices'],
                'combos': fill['combos'], 'show_n': fill['show_n'], 'case_sensitive': fill['case_sensitive'],
                'grading_notes': fill['grading_notes'],
                'values': [v for v in fill['values'] if v.get('kind') in SCAN_KINDS],
                'page_question': str(raw_item.get('page_question') or fill['question']),
                'page_answer': str(raw_item.get('page_answer') or ''),
                'page_choices': str(raw_item.get('page_choices') or ''),
                'fixed_reason': str(raw_item.get('fixed_reason') or '').strip(),
                'answer_whole': raw_item.get('answer_whole') is True,
                'answer_nonnegative': raw_item.get('answer_nonnegative') is True}
        #a page read by QuizScan: which printed problem it is, and its wording to write over it
        item['qs_id'] = raw_item.get('qs_id')
        item['page_text'] = str(raw_item.get('page_text') or '') if raw_item.get('values') else ''
        if paper:
            item.update(values=[], question=item['page_question'] or item['question'], fixed_reason='')
        item['use_page'] = not paper and (bool(item['fixed_reason']) or not item['values'])
        for ref in raw_item.get('picture_ids') or []:
            pid = ids.get(str(ref))
            pic = next((p for p in page['pictures'] if p['id'] == pid), None)
            if pic is not None and not pic['use'] and not paper:
                pic['use'] = 'item:{}:{}'.format(n, i)
        page['items'].append(item)
    for pic in page['pictures']:
        if not pic['use']:
            pic['use'] = 'quiz:{}'.format(n)
    return page


# ---------------------------------------------------------------- checking an item

def star_answer(choices, answer):
    """The choices with the answer's line marked * when none is marked yet and the answer is one of
    them (the owner, 2026-10-25: the AI wrote the right answer, "Pumpkin", but left the * off, and
    every problem on the page said to mark it by hand). Several answer lines (pick several) mark each."""
    lines = (choices or '').splitlines()
    if not lines or any(l.strip().startswith('*') for l in lines):
        return choices
    want = {' '.join(a.split()).lower() for a in (answer or '').splitlines() if a.strip()}
    if not want:
        return choices
    out = ['*' + l.strip() if ' '.join(l.split()).lower() in want else l for l in lines]
    return '\n'.join(out) if out != lines else choices


def item_problem(item, picture_files=()):
    """(qtype, title, question, answer, options) for a draft item, as the problem it would
    become. picture_files: its pictures (a stand-in name is enough for checking)."""
    paper = item.get('kind') == 'paper'
    use_page = item.get('use_page') and not paper
    qtype = 'paper' if paper else item.get('qtype') if item.get('qtype') in QTYPES else 'numeric'
    question = item.get('page_question') if use_page else item.get('question')
    answer = item.get('page_answer') if use_page else item.get('answer')
    choices = item.get('page_choices') if use_page and item.get('page_choices') else item.get('choices')
    if qtype in ('choice_one', 'choice_many'):
        choices = star_answer(choices, answer)
    options = {'markup': 'friendly', 'values': [] if (use_page or paper) else list(item.get('values') or []),
               'choices': choices or '', 'combos': '' if use_page else (item.get('combos') or ''), 'shuffle': True,
               'show_n': item.get('show_n'), 'case_sensitive': bool(item.get('case_sensitive')), 'precision': 'close',
               'ordered': False, 'answer_display': '', 'complex': False,
               'grading_notes': item.get('grading_notes') or '',
               'images': [{'file': f, 'label': ''} for f in picture_files]}
    if options['values'] and item.get('page_text'):
        options['page_text'] = item['page_text']
    return qtype, (item.get('title') or '').strip(), question or '', answer or '', options


def _numbers(text):
    out = []
    for part in F.split_list(text or '')[0]:
        try:
            out.append(float(str(part).replace(',', '').strip()))
        except ValueError:
            pass
    return out


def check_item(item, picture_files=('scan.jpg',), samples=3):
    """{'errors', 'warnings', 'samples': [(question, answer)]} for a draft item."""
    #a Paper only problem needs its picture; the crop is made on Save, so a stand-in is checked
    qtype, title, question, answer, options = item_problem(item, list(picture_files) if item.get('kind') == 'paper' else [])
    qt = get_qtype(qtype)
    errors = [] if title else ['Please give it a short title.']
    if len(title) > 64:
        errors.append('The title can be at most 64 characters.')
    if len(question) > 1024:
        errors.append('The question can be at most 1024 characters.')
    errors += qt.validate(question, answer, options)
    warnings, shown = [], []
    if errors:
        return {'errors': errors, 'warnings': warnings, 'samples': shown}
    rng = random.Random()
    negative = fraction = same_choices = None
    versions = set()
    for k in range(DRAWS if options['values'] else 1):
        try:
            prob, ansr, opts = qt.instantiate(question, answer, options, rng)
        except F.FriendlyError as exc:
            return {'errors': ['Some versions can’t be worked out: {}'.format(exc)], 'warnings': [], 'samples': []}
        versions.add(prob)
        shown_answer = qt.show_correct(ansr, opts)
        if len(shown) < samples:
            shown.append((prob, shown_answer, opts.get('choices') or []))
        if qtype == 'numeric':
            nums = _numbers(ansr)
            if item.get('answer_nonnegative') and any(x < 0 for x in nums) and negative is None:
                negative = (prob, shown_answer)
            if item.get('answer_whole') and any(abs(x - round(x)) > 1e-9 for x in nums) and fraction is None:
                fraction = (prob, shown_answer)
        choices = opts.get('choices') or []
        if len(set(choices)) < len(choices) and same_choices is None:
            same_choices = prob
    if negative:
        warnings.append('Some versions have a negative answer, e.g. “{}” → {}. Narrow the ranges.'.format(*negative))
    if fraction:
        warnings.append('Some versions don’t come out to a whole number, e.g. “{}” → {}.'.format(*fraction))
    if same_choices:
        warnings.append('Some versions show the same choice twice, e.g. “{}”.'.format(same_choices))
    if options['values'] and len(versions) < 4:
        warnings.append('Only {} different version{} can come up.'.format(len(versions), '' if len(versions) == 1 else 's'))
    return {'errors': [], 'warnings': warnings, 'samples': shown}


def _check_key(item):
    """What a check depends on: the problem as it would be made, but not its title (a title can
    follow the workbook's name; it's checked by itself in checked_item)."""
    qtype, _title, question, answer, options = item_problem(item, ['scan.jpg'] if item.get('kind') == 'paper' else [])
    return hashlib.sha1(json.dumps([qtype, question, answer, options, item.get('kind'), bool(item.get('answer_whole')),
                                    bool(item.get('answer_nonnegative')), DRAWS], sort_keys=True, default=str).encode()).hexdigest()


def checked_item(item):
    """check_item, kept on the item ('check') and done again only when its problem changes (the
    owner, 2026-10-21: the draft page drew every problem's versions again on each load, about 5
    seconds for 34 problems). "Draw again" (scan_check) still draws new versions."""
    key = _check_key(item)
    kept = item.get('check')
    if not (isinstance(kept, dict) and kept.get('key') == key and isinstance(kept.get('result'), dict)):
        kept = {'key': key, 'result': check_item(dict(item, title='x'))}
        item['check'] = kept
    result = kept['result']
    title = (item.get('title') or '').strip()
    errors = [] if title else ['Please give it a short title.']
    if len(title) > 64:
        errors.append('The title can be at most 64 characters.')
    if errors or result['errors']:
        return {'errors': errors + result['errors'], 'warnings': [], 'samples': []}
    return result


# ---------------------------------------------------------------- the review form

def _f(form, key, default=''):
    return form.get(key, default)


NOTE_LONGEST = 500   # letters in a "Read this page again" note


def read_again(data, n, note=''):
    """Page n of a draft, to be read again from the start (the owner, 2026-10-20): its reading
    and the teacher's changes to it are dropped; note, what was wrong with it, goes to the AI
    with the page. The other pages stay as they are."""
    page = {'n': int(n), 'state': 'waiting'}
    if data['pages'][int(n) - 1].get('spread'):
        page['spread'] = True
    if data['pages'][int(n) - 1].get('join_prev'):
        page['join_prev'] = True  # (its join to the page before stays: the owner, 2026-10-26)
    note = ' '.join((note or '').split())[:NOTE_LONGEST]
    if note:
        page['note'] = note
    data['pages'][int(n) - 1] = page
    return data


def joined_saves(data):
    """A page joined to the one before it is saved, or kept back, together with it."""
    lead = True
    for page in data.get('pages') or []:
        if page.get('state') != 'done' or page.get('kind') != 'problems':
            continue
        if page.get('join_prev'):
            page['save'] = lead
        else:
            lead = page.get('save') is not False


def update_from_form(data, form):
    """Take the review page's fields into the draft (only pages that were read)."""
    #(the names as the page showed them, so a title left as shown keeps following the workbook's name)
    if any(p.get('state') == 'done' for p in data.get('pages') or []):
        apply_names(data)
    data['name'] = _f(form, 'name', data.get('name', '')).strip()[:128]
    #(always the workbook's own folders, named after it: the owner, 2026-10-25; the Folder field is gone)
    data['folder'] = ''
    for page in data['pages']:
        if page.get('state') != 'done':
            #(a page not read yet can be joined to the one before already, the thumbnails' chain: the owner, 2026-10-26)
            jp = 'p{}-join_prev'.format(page['n'])
            if jp in form and page.get('state') != 'saved':
                page['join_prev'] = bool(form.get(jp))
            continue
        n = page['n']
        pre = 'p{}-'.format(n)
        if pre + 'shown' not in form:
            continue  # not on the page that was sent
        title = _f(form, pre + 'title', page['title']).strip()[:64]
        if title != page['title']:
            page['title_auto'] = False  # (typed by hand: kept as typed, the owner 2026-10-19)
        page['title'] = title
        page['join_prev'] = bool(form.get(pre + 'join_prev'))
        #(each page has its own Generate now, the owner 2026-10-25: no Save check box; Generate picks the page)
        page.pop('save', None)
        page['shuffle'] = bool(form.get(pre + 'shuffle'))
        page['calculator'] = bool(form.get(pre + 'calculator'))
        pics = []
        for pic in page['pictures']:
            key = pre + pic['id'] + '-'
            if form.get(key + 'removed'):
                continue
            pic['box'] = clean_box(_f(form, key + 'box', ''))
            pic['label'] = _f(form, key + 'label', pic['label']).strip()[:64]
            pic['use'] = _f(form, key + 'use', pic['use'])
            pic['keep'] = bool(form.get(key + 'keep')) or bool(pic['use'])
            pics.append(pic)
        #pictures added on the page: p3-new1-box ...
        for key in sorted(form.keys()):
            m = re.match(r'^p{}-(new\d{{1,3}})-box$'.format(n), key)
            if m and not form.get(pre + m.group(1) + '-removed'):
                pid = 'n{}'.format(len(pics) + 1 + sum(1 for p in pics if p['id'].startswith('n')))
                while any(p['id'] == pid for p in pics):
                    pid += 'x'
                use = _f(form, pre + m.group(1) + '-use', '')
                pics.append({'id': pid, 'box': clean_box(form[key]), 'label': _f(form, pre + m.group(1) + '-label', '').strip()[:64],
                             'keep': True, 'use': use})
        page['pictures'] = pics
        for i, item in enumerate(page['items']):
            ip = 'p{}i{}-'.format(n, i)
            item['include'] = bool(form.get(ip + 'include'))
            title = _f(form, ip + 'title', item['title']).strip()[:64]
            if title != item['title']:
                item['title_auto'] = False
            item['title'] = title
            if item['kind'] == 'paper':
                item['question'] = item['page_question'] = _f(form, ip + 'question', item['question'])
                item['answer'] = _f(form, ip + 'answer', item['answer'])
                item['box'] = clean_box(_f(form, ip + 'box', ''))
                continue
            #its place on the page, dragged there by hand (the blue box: the owner, 2026-10-20)
            if form.get(ip + 'placed') == '1' and ip + 'place' in form and item.get('qs_id') and isinstance(page.get('slots'), dict):
                #(a one-line place is under 2% of the page tall: it was taken for unreadable and made
                #the whole page, the owner 2026-10-20, "bible quiz2"; one that can't be read is left
                #unplaced, never the whole page)
                box = clean_box(_f(form, ip + 'place', ''), least=0.003)
                if box == {'left': 0.0, 'top': 0.0, 'right': 1.0, 'bottom': 1.0}:
                    box = None
            else:
                box = None
            if box is not None:
                slot = page['slots'].get(item['qs_id']) or {}
                if slot.get('kind') != 'field':
                    chars = [x.get('char') for x in page['slots'].values() if x.get('char')]
                    slot = {'kind': 'field', 'text': None, 'char': sorted(chars)[len(chars) // 2] if chars else round(0.6 * (box['bottom'] - box['top']), 5)}
                if slot.get('answer') != box:
                    #(moved: its wording is found again beside the new place when it's saved)
                    slot = dict(slot, answer=box, by_hand=True, text=None)
                    slot.pop('guessed', None)   # (placed by the teacher now: solid, like a found one)
                page['slots'][item['qs_id']] = slot
            qtype = _f(form, ip + 'qtype', item['qtype'])
            item['qtype'] = qtype if qtype in QTYPES else item['qtype']
            item['use_page'] = bool(form.get(ip + 'use_page'))
            item['new'] = bool(form.get(ip + 'new'))
            for field in ('question', 'answer', 'choices', 'page_question', 'page_answer', 'page_choices'):
                if ip + field in form:
                    item[field] = form[ip + field]
            values = []
            for k in range(20):
                vp = '{}v{}-'.format(ip, k)
                if vp + 'name' not in form:
                    break
                row = {'name': form[vp + 'name'].strip(), 'kind': _f(form, vp + 'kind', '')}
                for key in ('min', 'max', 'step', 'places', 'items', 'formula'):
                    if _f(form, vp + key).strip():
                        row[key] = form[vp + key].strip()
                if not row['name'] and len(row) == 2:
                    continue  # the empty row for adding one
                if row['kind'] not in SCAN_KINDS:
                    row['kind'] = 'whole'
                diff = [d.strip() for d in _f(form, vp + 'different_from').split(',') if d.strip()]
                if diff:
                    row['different_from'] = diff
                if form.get(vp + 'nonzero'):
                    row['nonzero'] = True
                values.append(row)
            item['values'] = values
    joined_saves(data)
    return data


def _folder_named(kind, name, parent=None):
    """The folder called `name` (any case) if there is one, wherever it is; otherwise a new one
    inside `parent` (or at the top). A workbook name used again files into the same folders
    (the owner, 2026-10-19)."""
    from . import services as S
    want = ' '.join((name or '').split())[:64]
    for g in S.subjects(kind):
        if (g.title or '').lower() == want.lower():
            return g
    try:
        made = S.create_subject(kind, want, parent)
    except S.ServiceError:
        return S.subject_named(kind, want)
    #(made by the scanner: its camera mark, the owner 2026-10-25; a folder of the same name already there isn't)
    if hasattr(made, 'from_scan'):
        made.from_scan = True
    return made


def workbook_plan(data):
    """How a scan's quizzes, problems and folders are named after its workbook (the owner,
    2026-10-19):
      - one page: the quiz is the workbook's name (in Uncategorized), its problems "Name-1",
        "Name-2"... in a Problems folder with the workbook's name;
      - several pages (a folder, several pictures or a PDF): the quizzes "Name 1", "Name 2"...
        in a Quizzes folder with the workbook's name; the problems "Name 2-3" (quiz 2's third)
        in a Problems folder with the workbook's name, one folder in it per quiz, named after it.
    The same workbook name used again: the same folders, and the quizzes carry on from the
    numbers already used ("Name 4", "Name 5"...; a second one-page quiz "Name 2").
    Returns {'base', 'multi', 'quizzes': [quiz names, in order]}."""
    from . import services as S
    base = ' '.join((data.get('name') or 'Workbook').split())[:57] or 'Workbook'
    multi = len(data.get('pages') or []) > 1
    count = max(len(quiz_groups(data)), 1)
    taken = {' '.join((vq.title or '').split()).lower() for vq in S.in_use('quizzes').all()}
    if multi:
        #(a quiz's problems get a folder named after it: that name must be free too)
        taken |= {(g.title or '').lower() for g in S.subjects('problems')}
    elif base.lower() not in taken:
        return {'base': base, 'multi': multi, 'quizzes': [base]}
    #the numbers after the highest already used: "Name 4" after "Name 3"
    pre = base.lower() + ' '
    used = [int(t[len(pre):]) for t in taken if t.startswith(pre) and t[len(pre):].isdigit()]
    start = max(used + [0 if multi else 1]) + 1
    return {'base': base, 'multi': multi, 'quizzes': ['{} {}'.format(base, start + k) for k in range(count)]}


def apply_names(data, plan=None):
    """The quiz and problem titles not typed by hand, named after the workbook (workbook_plan)."""
    plan = plan or workbook_plan(data)
    for g, (lead, pages) in enumerate(quiz_groups(data)):
        quiz = plan['quizzes'][g] if g < len(plan['quizzes']) else plan['quizzes'][-1]
        if lead.get('title_auto', True):
            lead['title'] = quiz
        k = 0
        for page in pages:
            for item in page.get('items') or []:  # (a cover has none)
                if not item.get('include'):
                    continue
                k += 1
                if item.get('title_auto', True):
                    item['title'] = '{}-{}'.format(quiz, k)[:64]
    return plan


def image_page(page):
    """A read page with no questions whose picture is kept: it becomes an Image only quiz of its
    own (the owner, 2026-10-19: "store it as a quiz instead of just storing the image")."""
    return page.get('state') == 'done' and page.get('kind') != 'problems' and page.get('save') is not False \
        and any(p.get('keep') for p in page.get('pictures') or [])


def quiz_groups(data):
    """[(lead page, [pages])]: each problems page with something included is a quiz, unless
    it's joined to the one before; a page with no questions whose picture is kept is a quiz of its
    own (an Image only one)."""
    groups = []
    pages_by_n = {p['n']: p for p in data['pages']}
    cover = None  # a page with no problems joined to the next one: its picture starts that page's quiz
    for page in data['pages']:
        if is_cover(page, pages_by_n.get(page['n'] + 1)):
            cover = page
            continue
        if image_page(page):
            groups.append((page, [page]))
            continue
        if page.get('state') != 'done' or page.get('kind') != 'problems' or not any(i['include'] for i in page['items']):
            continue
        #(a page kept back for later isn't saved now: the owner, 2026-10-22)
        if page.get('save') is False:
            continue
        #(joined to the last quiz with problems: an Image only page between them isn't one, and
        #joining to it lost the page's problems; found by the tests, 2026-10-20)
        prev = next((g for g in reversed(groups) if not image_page(g[0])), None)
        #(joined only to the page right before it, when that one is in a quiz with problems: a join made before the
        #pages were read is dropped if the page before turned out to be a picture or nothing to use; the owner 2026-10-26)
        before = page['n'] - 1
        if cover is not None and cover['n'] == before:
            #(its quiz opens with the page before's picture; the quiz is still this page's, its name and settings)
            groups.append((page, [cover, page]))
        elif page.get('join_prev') and prev is not None and prev[1][-1]['n'] == before:
            prev[1].append(page)
        else:
            groups.append((page, [page]))
        cover = None
    return groups


def is_cover(page, after):
    """A read page with no problems (a picture, a cover, nothing to use) joined to the page after it, a page with problems:
    its picture starts that page's quiz (the owner, 2026-10-27; it couldn't be joined)."""
    return bool(after) and after.get('join_prev') and page.get('state') == 'done' and page.get('kind') != 'problems' \
        and page.get('save') is not False and after.get('state') == 'done' and after.get('kind') == 'problems' \
        and after.get('save') is not False and any(i['include'] for i in after.get('items') or [])


def lead_of(data):
    """{page n: the n of the quiz it ends up in}."""
    out = {}
    for lead, pages in quiz_groups(data):
        for p in pages:
            out[p['n']] = lead['n']
    return out


def use_choices(data):
    """Where a picture can go: [(value, label)] for the review page's "Use with" lists."""
    out = [('', 'Nothing (just save it in Pictures)')]
    leads = lead_of(data)
    for page in data['pages']:
        if page.get('state') != 'done' or page.get('kind') != 'problems':
            continue
        if leads.get(page['n']) == page['n']:
            out.append(('quiz:{}'.format(page['n']), 'The quiz “{}” (top of the quiz)'.format(page['title'])))
        for i, item in enumerate(page['items']):
            if item['kind'] != 'paper':
                out.append(('item:{}:{}'.format(page['n'], i), 'Page {}, #{}: {}'.format(page['n'], i + 1, item['title'])))
    return out


NO_PLACE = 'No place on the page yet. Drag its blue box onto its blank.'


def place_of(page, item):
    """Where a drafted problem is answered on its page (the owner, 2026-10-20: a scanned quiz has no
    ordinary questions; every blank gets a place, found or put there by hand): (box, found), or
    None for one that needs no box (choices answered by their marks, paper only, not a scanned
    page). A missing one's box starts at the end of its printed line."""
    if page.get('kind') != 'problems' or item.get('kind') != 'question' or not item.get('qs_id') \
            or not isinstance(page.get('slots'), dict):
        return None
    line = next((q.get('box') for q in page.get('qs') or [] if q.get('id') == item['qs_id']), None)
    if not isinstance(line, dict):
        return None
    slot = page['slots'].get(item['qs_id']) or {}
    if slot.get('kind') in ('choices', 'paper'):
        return None
    if slot.get('kind') == 'field' and isinstance(slot.get('answer'), dict):
        return slot['answer'], True
    w = line['right'] - line['left']
    return {'left': round(max(line['left'], line['right'] - max(0.08, 0.25 * w)), 4), 'top': line['top'],
            'right': line['right'], 'bottom': line['bottom']}, False


def label_of(page, item):
    """The page's own number for a drafted problem ("7 b."), else its page and place on it ("2-6"):
    short, so a box's label always fits on it (the owner, 2026-10-22; it was the title, cut off)."""
    from .routes import _label
    q = next((q for q in page.get('qs') or [] if q.get('id') == item.get('qs_id')), None)
    k = next((i for i, x in enumerate(page.get('items') or []) if x is item), None)
    return _label((q or {}).get('number')) or ('{}-{}'.format(page.get('n'), k + 1) if k is not None else item.get('title') or '')


def missing_places(data):
    """[(page n, item i, label)]: problems that will be saved with no place on their page."""
    out = []
    for _lead, pages in quiz_groups(data):
        for page in pages:
            for i, item in enumerate(page.get('items') or []):
                place = place_of(page, item) if item.get('include') else None
                if place and not place[1]:
                    out.append((page['n'], i, label_of(page, item)))
    return out


def check_all(data):
    """Everything wrong with the draft, as {key: [errors]} ('page:3:item:2', 'folder', ...)."""
    from . import services as S
    problems = {}
    if data.get('folder'):
        err = S.new_subject_name_error('problems', data['folder'])
        if err:
            problems['folder'] = [err]
    seen = {}
    for lead, pages in quiz_groups(data):
        title = ' '.join((lead.get('title') or '').split())
        if not title:
            problems['page:{}:title'.format(lead['n'])] = ['Please give the quiz a title.']
        elif S.quiz_name_taken(title) or title.lower() in seen:
            #(a quiz already called that, or another page of this scan with the same title)
            problems['page:{}:title'.format(lead['n'])] = [S.QUIZ_NAME_TAKEN.format(title)]
        seen[title.lower()] = lead['n']
        for page in pages:
            for i, item in enumerate(page['items']):
                if not item['include']:
                    continue
                errors = checked_item(item)['errors']
                if errors:
                    problems['page:{}:item:{}'.format(page['n'], i)] = errors
    for n, i, _label in missing_places(data):
        problems.setdefault('page:{}:item:{}'.format(n, i), []).append(NO_PLACE)
    if not quiz_groups(data) and not any(p.get('keep') for page in data['pages'] if page.get('state') == 'done'
                                         for p in page.get('pictures', [])):
        problems['nothing'] = ['There’s nothing to save yet: no page has a problem checked or a picture to keep.']
    return problems


# ---------------------------------------------------------------- save

def _slug(text):
    text = re.sub(r'[^A-Za-z0-9]+', '-', text or '').strip('-').lower()
    return text[:40] or 'page'


def save_picture(job, page_n, box, name):
    """Crop a box from a page into the pictures folder. Returns its file name."""
    from PIL import Image
    from app.upload.routes import unique_name, trythumb, static_dir
    from werkzeug.utils import secure_filename
    #(cut from the full-size page when there is one: the owner, 2026-10-20)
    src = full_file(job.id, page_n) if os.path.exists(full_file(job.id, page_n)) else page_file(job.id, page_n)
    with Image.open(src) as im:
        w, h = im.size
        crop = im.crop((int(box['left'] * w), int(box['top'] * h), max(int(box['right'] * w), 1), max(int(box['bottom'] * h), 1)))
        fname = unique_name(secure_filename('{}.jpg'.format(name)) or 'scan.jpg')
        crop.convert('RGB').save(os.path.join(static_dir(), fname), 'JPEG', quality=88)
    trythumb(static_dir(), fname, quiet=True)
    from app.upload.routes import files_changed
    files_changed()
    return fname


def page_layout_of(job, pages, places, ids, shuffled=False):
    """The layout a quiz made from these pages is taken on (pagelayout.py): each page's
    picture, copied into static/pagequiz/, and each problem's place on it by its position
    in the quiz. A problem left out of the quiz is covered over, and one whose place wasn't
    found is taken the usual way, under the page. None when no problem has a place."""
    import uuid
    from app.upload.routes import static_dir
    from . import pagelayout
    folder = os.path.join(static_dir(), 'pagequiz')
    os.makedirs(folder, exist_ok=True)
    out = {'v': 1, 'ids': list(ids), 'font': 'fonts/' + (pages[0].get('font') or 'NotoSans-Bold.ttf'), 'pages': [], 'slots': [], 'labels': {}}
    if shuffled:
        return None
    where = {(page['n'], i): pos for pos, (page, i) in enumerate(places, 1)}
    for k, page in enumerate(pages):
        qs = {p['id']: p for p in page.get('qs') or []}
        hide = []
        for i, item in enumerate(page['items']):
            slot = dict(page['slots'].get(item.get('qs_id') or '') or {})
            pos = where.get((page['n'], i))
            if pos is not None:
                #(the page's own number for it, e.g. "1 a.": routes.page_labels, the owner, 2026-10-20)
                from .routes import _label
                out['labels'][pos] = _label((qs.get(item.get('qs_id')) or {}).get('number'))
            if pos is None:
                #left out: covered, so nobody answers it
                box = (qs.get(item.get('qs_id')) or {}).get('box')
                if box:
                    hide.append(box)
                continue
            if not slot or slot['kind'] == 'paper':
                if slot.get('kind') == 'paper':
                    out['slots'].append({'pos': pos, 'page': k, 'kind': 'paper'})
                continue
            if slot['kind'] == 'field':
                changes = bool(item.get('values')) and not item.get('use_page') and item.get('page_text')
                if changes and not slot.get('text') and slot.get('by_hand'):
                    #(placed by hand: its wording found beside the new place, the owner 2026-10-20)
                    line = qs.get(item.get('qs_id')) or {}
                    if isinstance(line.get('box'), dict):
                        from PIL import Image
                        with Image.open(page_file(job.id, page['n'])) as im:
                            text, paper = pagelayout.wording_box(im.convert('RGB'), line, slot['answer'])
                        if text:
                            slot['text'] = text
                            if paper:
                                slot['paper'] = paper
                if changes and not slot.get('text'):
                    continue  # its printed numbers couldn't be covered: taken the usual way
                if not changes:
                    slot['text'] = None
            if slot['kind'] == 'choices':
                printed = (qs.get(item['qs_id']) or {}).get('choices') or []
                if item['qtype'] == 'truefalse' and not printed:
                    text = ((qs.get(item['qs_id']) or {}).get('text') or '').lower()
                    printed = sorted(['True', 'False'], key=lambda w: text.find(w.lower()) if w.lower() in text else 99)
                slot['choices'] = printed
            out['slots'].append(dict(slot, pos=pos, page=k))
        name = 'pagequiz/{}.jpg'.format(uuid.uuid4().hex)
        #(an answer key's colored, or bold, right answers made like the rest, so the page doesn't
        #give them away: pagelayout.clean_answer_key, the owner 2026-10-19)
        from PIL import Image
        with Image.open(page_file(job.id, page['n'])) as im:
            pic, _changed = pagelayout.erase_answers(im.convert('RGB'), page['slots'])
            pic, _changed = pagelayout.clean_answer_key(pic, {'problems': page.get('qs') or []}, page['slots'],
                                                       os.path.join(current_app.static_folder, 'fonts'))
            #(on the page as students get it: an answer key's erased answers are blank paper there,
            #the code critic 2026-10-22)
            pagelayout.mark_bare(pic, [s for s in out['slots'] if s.get('page') == k])
            pic.save(os.path.join(static_dir(), name), 'JPEG', quality=90)
        size = page.get('size') or {}
        #(QuizScan's boxes are kept too, so the places can be found again later without reading the page again)
        out['pages'].append({'image': name, 'width': size.get('width'), 'height': size.get('height'), 'hide': hide,
                             'qs': page.get('qs') or [], 'items': [item.get('qs_id') for item in page['items']]})
    #(the page is shown even when no answer place was found on it: the problems are then all
    #answered under it, the owner 2026-10-18)
    return out


def reused_as(data, ignore_new=False):
    """{(page n, item i): title} for the included items that Save would not make, because they
    are the same as a problem already in the library or an item before them in the scan
    (S.problem_key; the owner, 2026-10-18). An item with pictures is always made: its pictures
    are new files. An item checked "Make a new one instead" is left out, unless ignore_new."""
    from . import services as S
    out, seen = {}, {}
    for page in data.get('pages') or []:
        if page.get('state') != 'done' or page.get('kind') != 'problems':
            continue
        linked = {int(m.group(1)) for pic in page.get('pictures', [])
                  for m in [re.match(r'^item:{}:(\d+)$'.format(page['n']), pic.get('use') or '')] if m}
        for i, item in enumerate(page.get('items') or []):
            if not item.get('include') or item.get('kind') == 'paper' or i in linked:
                continue
            qtype, title, question, answer, options = item_problem(item)
            if checked_item(item)['errors']:
                continue
            key = S.problem_key(qtype, question, answer, options)
            #(as save_all does: a new one is made, and the same items after it use it)
            if item.get('new') and not ignore_new:
                seen[key] = title
                continue
            if key not in seen:
                vp = S.same_problem(qtype, question, answer, options)
                if vp is None:
                    seen[key] = title
                    continue
                seen[key] = vp.title or 'Untitled'
            out[(page['n'], i)] = seen[key]
    return out


def save_all(job, data, author):
    """Make the pictures, problems and quizzes. Call check_all first: this assumes the draft is
    fine. Returns {'quizzes': [VQuiz], 'problems': n, 'pictures': [file names]}. All or nothing:
    if anything fails partway, what was already made is removed again, so pressing Save again
    doesn't make it twice (the code critic, 2026-10-20)."""
    made_so_far = {'quizzes': [], 'problems': [], 'pictures': []}
    try:
        return _save_all(job, data, author, made_so_far)
    except Exception:
        db.session.rollback()
        _unmake(made_so_far)
        raise


def _unmake(made):
    """Remove the quizzes, problems and picture files a failed save had already made."""
    from app.upload.routes import static_dir
    for vq in made['quizzes']:
        row = db.session.get(VQuiz, vq.id) if vq.id is not None else None
        if row is not None:
            #(its page picture copied for taking the quiz on the page, too)
            for pg in (row.page_layout or {}).get('pages') or []:
                if pg.get('image'):
                    made['pictures'].append(pg['image'])
            db.session.delete(row)
    for pid in made['problems']:
        vp = db.session.get(VProblem, pid)
        if vp is not None:
            db.session.delete(vp)
    db.session.commit()
    for name in made['pictures']:
        for f in (name, 'T_' + name):
            try:
                os.remove(os.path.join(static_dir(), f))
            except OSError:
                pass
    if made['pictures']:
        from . import uploads
        uploads.sync()


def _save_all(job, data, author, made_so_far):
    from . import services as S
    book = _slug(data.get('name') or job.name)
    leads = lead_of(data)
    pictures, for_item, for_quiz, kept_of = made_so_far['pictures'], {}, {}, {}
    #1. the pictures, cropped into the pictures folder (not a page kept back for later). A picture on a page not
    #made now goes too when it's for a problem or quiz made now: pages are made one at a time, so a picture on
    #page 2 for the top of page 1's quiz would otherwise never reach it (the tests, 2026-10-25)
    now = {p['n'] for p in data['pages'] if p.get('state') == 'done' and p.get('save') is not False}
    def for_now(use):
        m = re.match(r'^(?:item|quiz):(\d+)', use or '')
        return bool(m) and leads.get(int(m.group(1)), int(m.group(1))) in {leads.get(n, n) for n in now}
    for page in data['pages']:
        if page.get('state') != 'done':
            continue
        here = page['n'] in now
        for pic in page.get('pictures', []):
            if not (pic.get('keep') or pic.get('use')) or (not here and not for_now(pic.get('use'))):
                continue
            fname = save_picture(job, page['n'], pic['box'], '{}-p{}-{}'.format(book, page['n'], _slug(pic.get('label'))))
            pictures.append(fname)
            if pic.get('keep') and here:
                kept_of.setdefault(page['n'], []).append(fname)
            use = pic.get('use') or ''
            m = re.match(r'^item:(\d+):(\d+)$', use)
            if m:
                for_item.setdefault((int(m.group(1)), int(m.group(2))), []).append(fname)
            m = re.match(r'^quiz:(\d+)$', use)
            if m:
                for_quiz.setdefault(leads.get(int(m.group(1)), int(m.group(1))), []).append(fname)
    #2. the problems, and 3. one quiz per page (or joined pages)
    quizzes, made, reused, by_quiz = made_so_far['quizzes'], made_so_far['problems'], [], []
    #(the same problem twice, on a page or already in the library, is made once and used again:
    #the owner, 2026-10-18)
    by_key = {}
    for lead, pages in quiz_groups(data):
        ids, places = [], []
        if image_page(lead):
            #a page with no questions: an Image only quiz, its one problem the page's picture
            files = kept_of.get(lead['n'])[:1]
            vp = VProblem(author_id=author.id, from_scan=True)
            errors = S.save_problem(vp, 'look', '{}-1'.format(lead['title'])[:64], '', '', {'markup': 'friendly', 'values': [],
                                    'images': [{'file': f, 'label': ''} for f in files]})
            if errors:
                raise ScanError('“{}” couldn’t be saved: {}'.format(lead['title'], ' '.join(errors)))
            made.append(vp.id)
            vq = VQuiz(from_scan=True)
            quizzes.append(vq)
            errors = S.save_vquiz(vq, lead['title'], [vp.id], author_id=author.id, shuffle_order=False, calculator_ok=False)
            if errors:
                raise ScanError('The quiz “{}” couldn’t be saved: {}'.format(lead['title'], ' '.join(errors)))
            by_quiz.append([vp.id])
            continue
        for page in pages:
            if page.get('kind') != 'problems':
                #a cover joined to this quiz: its picture first, as an Image only problem (the owner, 2026-10-27); the picture
                #kept on it, else the whole page
                files = (kept_of.get(page['n']) or [])[:1] or [save_picture(job, page['n'], {'left': 0, 'top': 0, 'right': 1, 'bottom': 1},
                                                                           '{}-p{}-page'.format(book, page['n']))]
                if files[0] not in pictures:
                    pictures.append(files[0])
                vp = VProblem(author_id=author.id, from_scan=True)
                errors = S.save_problem(vp, 'look', '{}-1'.format(page.get('title') or lead['title'])[:64], '', '',
                                        {'markup': 'friendly', 'values': [], 'images': [{'file': f, 'label': ''} for f in files]})
                if errors:
                    raise ScanError('“{}” couldn’t be saved: {}'.format(page.get('title') or lead['title'], ' '.join(errors)))
                made.append(vp.id)
                ids.append(vp.id)
                continue
            for i, item in enumerate(page['items']):
                if not item['include']:
                    continue
                places.append((page, i))
                files = list(for_item.get((page['n'], i), []))
                if item['kind'] == 'paper':
                    files = [save_picture(job, page['n'], item['box'], '{}-p{}-{}'.format(book, page['n'], _slug(item['title'])))] + files
                    pictures.append(files[0])
                qtype, title, question, answer, options = item_problem(item, files)
                key = S.problem_key(qtype, question, answer, options)
                same = None if item.get('new') else by_key.get(key) or S.same_problem(qtype, question, answer, options)
                if same is not None:
                    by_key[key] = same
                    ids.append(same.id)
                    if same.id not in made and same.id not in reused:
                        reused.append(same.id)
                    continue
                vp = VProblem(author_id=author.id, from_scan=True)
                errors = S.save_problem(vp, qtype, title, question, answer, options, page.get('calculator'))
                if errors:
                    raise ScanError('“{}” couldn’t be saved: {}'.format(title, ' '.join(errors)))
                by_key[key] = vp
                ids.append(vp.id)
                made.append(vp.id)
        vq = VQuiz(from_scan=True)
        quizzes.append(vq)
        images = for_quiz.get(lead['n']) or []
        errors = S.save_vquiz(vq, lead['title'], ids, author_id=author.id, shuffle_order=bool(lead.get('shuffle')),
                              calculator_ok=bool(lead.get('calculator')), image=images[0] if images else None)
        if errors:
            raise ScanError('The quiz “{}” couldn’t be saved: {}'.format(lead['title'], ' '.join(errors)))
        by_quiz.append(list(dict.fromkeys(ids)))
        if all(page.get('slots') is not None for page in pages):
            vq.page_layout = page_layout_of(job, pages, places, ids, shuffled=bool(lead.get('shuffle')))
            vq.save()
    #4. filed: in the folder typed on the draft, if one was; otherwise in folders named after the
    #workbook (workbook_plan; the owner, 2026-10-19)
    folder = data.get('folder')
    if folder:
        if made:
            S.file_items('problems', made, S.subject_named('problems', folder))
        if quizzes:
            S.file_items('quizzes', [q.id for q in quizzes], S.subject_named('quizzes', folder))
    elif quizzes:
        plan = data.get('_plan') or {'base': data.get('name') or 'Workbook', 'multi': len(data['pages']) > 1}
        top = _folder_named('problems', plan['base'])
        if plan['multi']:
            S.file_items('quizzes', [q.id for q in quizzes], _folder_named('quizzes', plan['base']))
            for vq, ids_in in zip(quizzes, by_quiz):
                S.file_items('problems', ids_in, _folder_named('problems', vq.title, top))
        else:
            S.file_items('problems', [i for ids_in in by_quiz for i in ids_in], top)
            #(one page's quiz too, in the Quizzes folder of the workbook's name, like several
            #pages' quizzes: the owner, 2026-10-20; it was left uncategorized)
            S.file_items('quizzes', [q.id for q in quizzes], _folder_named('quizzes', plan['base']))
    #5. its pictures (a cover, a page's pictures) in a Pictures folder of the same name, so they
    #stay with the workbook (the owner, 2026-10-19)
    if pictures:
        from . import uploads
        uploads.sync()
        name = folder or (data.get('_plan') or {}).get('base') or data.get('name') or job.name or 'Workbook'
        home = S.subject_named('pictures', name) if folder else _folder_named('pictures', name)
        rows = [uploads.get(f) for f in dict.fromkeys(pictures)]
        S.file_items('pictures', [u.id for u in rows if u is not None], home)
    return {'quizzes': quizzes, 'problems': len(made), 'reused': len(reused), 'pictures': pictures}


# ---------------------------------------------------------------- the stash's folders

def _stash_name_taken(name, parent_id, ignore=None):
    low = name.lower()
    return any(f.name.lower() == low and f.id != ignore for f in ScanFolder.query.filter_by(parent_id=parent_id))


def create_folder(name, parent_id=None):
    """A stash folder (the owner, 2026-10-23), at the top or inside another; FolderError says what's wrong."""
    from app import folder_tree as FT
    name = FT.clean_name(name)
    parent = db.session.get(ScanFolder, parent_id) if parent_id else None
    FT.check_new(ScanFolder, parent)
    if _stash_name_taken(name, parent.id if parent else None):
        raise FT.FolderError('There’s already a folder called “{}” here.'.format(name))
    folder = ScanFolder(name=name, parent_id=parent.id if parent else None)
    db.session.add(folder)
    db.session.commit()
    return folder


def rename_folder(folder, name):
    from app import folder_tree as FT
    name = FT.clean_name(name)
    if _stash_name_taken(name, folder.parent_id, ignore=folder.id):
        raise FT.FolderError('There’s already a folder called “{}” here.'.format(name))
    folder.name = name
    db.session.commit()
    return folder


def move_folder(folder, to_id):
    """A stash folder inside another (None, or "top": the top), with the folders inside it; FolderError says what's wrong."""
    from app import folder_tree as FT
    target = db.session.get(ScanFolder, int(to_id)) if to_id and str(to_id) != 'top' else None
    if (target.id if target else None) == folder.parent_id:
        return folder
    FT.check_move(ScanFolder, folder, target)
    if _stash_name_taken(folder.name, target.id if target else None, ignore=folder.id):
        raise FT.FolderError('There’s already a folder called “{}” there. Rename one of them first.'.format(folder.name))
    folder.parent_id = target.id if target else None
    db.session.commit()
    return folder


def delete_folder(folder):
    """Nothing in it is deleted: its scans and folders move up a level (the top: Uncategorized). Returns how many
    scans and folders moved."""
    scans = ScanJob.query.filter_by(folder_id=folder.id).all()
    inner = ScanFolder.query.filter_by(parent_id=folder.id).all()
    for job in scans:
        job.folder_id = folder.parent_id
    for sub in inner:
        sub.parent_id = folder.parent_id
    db.session.flush()
    db.session.delete(folder)
    db.session.commit()
    return len(scans), len(inner)


def move_scan(job, folder_id):
    """A stashed scan into a folder (None: Uncategorized)."""
    job.folder_id = int(folder_id) if folder_id else None
    db.session.commit()
