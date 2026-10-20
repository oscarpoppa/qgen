"""Scan workbook pages: photos or a PDF of a paper workbook become problems and quizzes.

1. Upload: the pages are turned upright, scaled down and kept in a private folder
   (SCAN_DIR, not under static) with a ScanJob row holding the draft as JSON.
2. Reading: the AI reads one page per call, in a background thread (a page takes longer
   than a web request may), and the review page checks on it. Each page counts as one
   AI call against the hourly limit, and is logged like the other AI buttons.
3. The draft: the teacher checks every page beside its picture, adjusts crop boxes,
   random values and settings. Nothing is saved until Save.
4. Save: everything is checked first; only then are the pictures cropped into the
   pictures folder and the problems and one quiz per page (or joined pages) made.

Exercises done on paper (drawing, coloring, circling) become Paper only problems with
their crop as the picture. A page that is only a picture is saved to the pictures folder
and can go in the picture section of a quiz or problem.
"""
import io
import json
import os
import random
import re
import shutil
import threading
from datetime import datetime, timedelta

from flask import current_app

from . import db
from .models import ScanJob, VProblem, VQuiz, AICall
from .qtypes import get_qtype, REGISTRY
from . import friendly as F

MAX_PAGES = 30          # pages in one batch
LONG_SIDE = 1600        # pixels: pages are scaled down to this (the AI reads them at about this size)
STALE = timedelta(minutes=10)   # a page "reading" longer than this was cut off (the site restarted)
KEEP = timedelta(days=30)       # unfinished scans untouched this long are removed
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


def load_pages(files, folder=False):
    """Uploaded files (photos and PDFs) -> page pictures: upright, RGB, long side at most
    LONG_SIDE. Raises ScanError for files that can't be read or too many pages.
    folder: the files of a whole folder (the owner, 2026-10-19): taken in file-name order, and
    anything in it that isn't a picture or a PDF (notes, system files) is skipped, not an error.
    Returns (pages, names of the files skipped)."""
    from PIL import Image, ImageOps
    pages, skipped = [], []
    if folder:
        files = sorted(files, key=lambda f: _natural(f.filename))

    def room(more=1):
        if len(pages) + more > MAX_PAGES:
            raise ScanError('That’s more than {} pages. Please scan them in smaller batches.'.format(MAX_PAGES))

    for f in files:
        data = f.read()
        name = f.filename or 'a file'
        if not data:
            continue
        if data[:5] == b'%PDF-':
            import pypdfium2 as pdfium
            try:
                doc = pdfium.PdfDocument(data)
            except Exception:
                if folder:
                    skipped.append(name)
                    continue
                raise ScanError('“{}” couldn’t be opened as a PDF (it may be damaged or have a password).'.format(name))
            try:
                room(len(doc))
                for page in doc:
                    w, h = page.get_size()
                    scale = LONG_SIDE / max(w, h, 1)
                    pages.append(page.render(scale=scale).to_pil().convert('RGB'))
            finally:
                doc.close()
            continue
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
        except Exception:
            if folder:
                skipped.append(name)
                continue
            raise ScanError('“{}” isn’t a photo or PDF that can be read. Please use JPG, PNG or PDF.'.format(name))
        room()
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((LONG_SIDE, LONG_SIDE))
        pages.append(im)
    if not pages:
        if folder:
            raise ScanError('That folder has no photos or PDFs to scan.')
        raise ScanError('Please choose at least one photo or PDF of a workbook page.')
    return pages, skipped


def create_job(author, name, pages):
    """A new scan with these page pictures, nothing read yet."""
    job = ScanJob(author_id=author.id, name=(name or '').strip()[:128] or 'Workbook', pages=len(pages), status='new',
                  data=json.dumps({'pages': [{'n': i + 1, 'state': 'waiting'} for i in range(len(pages))]}))
    db.session.add(job)
    db.session.commit()
    os.makedirs(job_dir(job.id), exist_ok=True)
    for i, im in enumerate(pages):
        im.save(page_file(job.id, i + 1), 'JPEG', quality=85)
    return job


def remove_job(job):
    shutil.rmtree(job_dir(job.id), ignore_errors=True)
    db.session.delete(job)
    db.session.commit()


def remove_user_jobs(user):
    """When a user is deleted: their unfinished scans and page files."""
    for job in ScanJob.query.filter_by(author_id=user.id).all():
        shutil.rmtree(job_dir(job.id), ignore_errors=True)
        db.session.delete(job)


def remove_old_jobs(now=None):
    """Unfinished scans nobody has touched for a month. Returns how many."""
    now = now or datetime.now()
    old = ScanJob.query.filter(ScanJob.updated_at < now - KEEP).all()
    for job in old:
        remove_job(job)
    return len(old)


def get_data(job):
    return json.loads(job.data or '{}')


def put_data(job, data):
    job.data = json.dumps(data)
    job.updated_at = datetime.now()


# ---------------------------------------------------------------- reading (the AI)

def start_reading(job, api_key, user_id):
    """Read the job's unread pages (and any that failed) in the background. False when
    it's already being read."""
    now = datetime.now()
    data = get_data(job)
    for p in data['pages']:
        if p['state'] == 'error':
            p['state'] = 'waiting'
        if p['state'] == 'waiting':
            p.pop('error', None)
    #(read again: no longer paused nor a kept draft, the owner 2026-10-19)
    for k in ('paused', 'pausing', 'kept_at'):
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


def _read_all(app, job_id, api_key, user_id, run=None):
    with app.app_context():
        try:
            while True:
                job = db.session.get(ScanJob, job_id)
                if job is None:
                    return  # discarded meanwhile
                data = get_data(job)
                if data.get('run') != run:
                    return  # read again since: this reading stops
                if data.get('pausing'):
                    #Pause: the page being read was finished; the rest wait for Resume
                    _paused(data)
                    put_data(job, data)
                    job.status = 'ready'
                    db.session.commit()
                    return
                page = next((p for p in data['pages'] if p['state'] in ('waiting', 'reading')), None)
                if page is None:
                    data.pop('pausing', None)
                    put_data(job, data)
                    break
                page['state'] = 'reading'
                page['since'] = datetime.now().isoformat(timespec='seconds')
                put_data(job, data)
                db.session.commit()
                result = read_one(job, page['n'], api_key, user_id)
                job = db.session.get(ScanJob, job_id)
                if job is None:
                    return
                data = get_data(job)
                if data.get('run') != run:
                    #read again meanwhile: a page read all the way is kept (it's paid for)
                    if result.get('state') == 'done':
                        data['pages'][page['n'] - 1] = result
                        put_data(job, data)
                        db.session.commit()
                    return
                data['pages'][page['n'] - 1] = result
                put_data(job, data)
                db.session.commit()
                if result.get('stop'):
                    #the hourly limit: the rest stay unread until the teacher asks again
                    break
            job = db.session.get(ScanJob, job_id)
            if job is not None:
                job.status = 'ready'
                _tell_done(job)
                db.session.commit()
        except Exception as exc:
            db.session.rollback()
            app.logger.exception('reading scan {} failed: {}'.format(job_id, exc))
            job = db.session.get(ScanJob, job_id)
            if job is not None:
                data = get_data(job)
                for p in data['pages']:
                    if p['state'] in ('waiting', 'reading'):
                        p.update(state='error', error='Something went wrong while reading this page. Please try again.')
                put_data(job, data)
                job.status = 'ready'
                db.session.commit()
        finally:
            db.session.remove()


def _tell_done(job):
    """A notice for the teacher when a scan has been read all the way (not when it was canceled
    or stopped at the hourly limit) (the owner, 2026-10-18)."""
    from app.messages.models import notify
    pages = get_data(job).get('pages') or []
    if any(p.get('state') in ('waiting', 'reading') for p in pages):
        return
    done = sum(1 for p in pages if p.get('state') == 'done')
    failed = len(pages) - done
    if not failed:
        body = 'Your scan “{}” has been read and is ready to check.'.format(job.name)
    elif done:
        body = 'Your scan “{}” has been read: {} of {} pages are ready to check; {} couldn’t be read.'.format(job.name, done, len(pages), failed)
    else:
        body = 'Your scan “{}” couldn’t be read. Open it to try again.'.format(job.name)
    notify(job.author_id, body, '/quiz/scan/{}'.format(job.id))


PAUSED_NOTE = 'Paused before this page was read.'


def _paused(data):
    """The reading stopped by Pause: the pages not read yet wait, with a note, for Resume."""
    data['run'] = None
    data.pop('pausing', None)
    data['paused'] = True
    for p in data['pages']:
        if p['state'] in ('waiting', 'reading'):
            p.update(state='waiting', error=PAUSED_NOTE)


def pause_reading(job, reading):
    """Pause (the owner, 2026-10-19; it was Cancel): the page being read is finished (it's paid
    for), then the reading stops; Resume goes on with the rest. reading: whether it's still going
    (when it isn't, e.g. the site restarted meanwhile, it's paused at once)."""
    data = get_data(job)
    if reading:
        data['pausing'] = True
    else:
        _paused(data)
        job.status = 'ready'
    put_data(job, data)
    db.session.commit()


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


def read_one(job, n, api_key, user_id):
    """Read page n: QuizScan reads the page (exactly, and where everything is), then the AI
    gives its problems random numbers, then the page picture is leveled and searched for the
    places students answer (pagelayout.py), then the AI checks those places (check_places).
    Three to five AI calls, all counted against the hourly limit.
    Returns the page's draft, or {'state': 'error', ...} (the owner, 2026-10-18)."""
    from app import tuning
    from . import ai_helper, pagelayout
    hourly = tuning.get('ai_hourly')
    since = datetime.now() - timedelta(hours=1)
    if AICall.query.filter(AICall.user_id == user_id, AICall.created >= since).count() + 2 > hourly:
        return {'n': n, 'state': 'waiting', 'stop': True,
                'error': 'You’ve used the AI helper {} times in the last hour, so this page is waiting. '
                         'Press “Read the rest” in a while.'.format(hourly)}
    try:
        import quizscan
    except ImportError:
        return {'n': n, 'state': 'error', 'error': 'The page reader (QuizScan) isn’t installed on this site.'}
    path = page_file(job.id, n)
    #(read before, and only the numbers failed: QuizScan's reading is kept, so it isn't paid for twice)
    qs = (get_data(job)['pages'][n - 1] or {}).get('qs_reading')
    if qs is None:
        call = AICall(user_id=user_id, created=datetime.now(), kind='scan', request='Scan {} page {}'.format(job.id, n), ok=False)
        try:
            try:
                qs = quizscan.convert_image(path, api_key=api_key, model=tuning.get('ai_model'))[0]
                call.ok = True
            except quizscan.QuizScanError as exc:
                return {'n': n, 'state': 'error', 'error': str(exc)}
        finally:
            db.session.add(call)
            db.session.commit()
        #the page as QuizScan read it: flattened and leveled, so every box is a place on it; then
        #made truly level (its rows straight across, its margins straight down, the paper's dark
        #edge painted out) and QuizScan's boxes laid on its own printed lines (the owner, 2026-10-20)
        flat, qs = pagelayout.level_page(quizscan.flat_page(path, qs).convert('RGB'), qs)
        qs = pagelayout.snap_boxes(flat, qs)
        flat.save(path, 'JPEG', quality=90)
        #(kept at once, so a reading cut off from here on, e.g. by the site restarting, doesn't pay
        #for QuizScan again: the owner, 2026-10-18)
        fresh = db.session.get(ScanJob, job.id)
        if fresh is not None:
            data = get_data(fresh)
            data['pages'][n - 1]['qs_reading'] = qs
            put_data(fresh, data)
            db.session.commit()
    from PIL import Image
    flat = Image.open(path).convert('RGB')
    numbers = {}
    call = AICall(user_id=user_id, created=datetime.now(), kind='scan', request='Scan {} page {}: numbers'.format(job.id, n), ok=False)
    try:
        numbers, usage = ai_helper.page_numbers(api_key, qs)
        call.ok = True
        call.input_tokens, call.output_tokens = usage['input_tokens'], usage['output_tokens']
    except ai_helper.AIError as exc:
        return {'n': n, 'state': 'error', 'error': str(exc), 'qs_reading': qs}
    finally:
        db.session.add(call)
        db.session.commit()
        current_app.logger.info('scan {} page {} read (numbers ok={}, tokens in/out {}/{})'.format(
            job.id, n, call.ok, call.input_tokens, call.output_tokens))
    covered = {pid for pid, item in numbers.items() if item.get('values') and item.get('page_text')}
    slots = pagelayout.find_slots(flat, qs, covered)
    #(the AI looks at the page as a student will see it, and the places it moves are checked here)
    slots, checked = check_places(job, n, flat, qs, slots, covered, api_key, user_id)
    samples = {}
    for p in qs['problems']:
        if p['id'] in covered:
            words = p['text'][len(p.get('number') or ''):] if p['text'].startswith(p.get('number') or '\0') else p['text']
            samples[p['id']] = words.replace('_', '').strip()
    font = pagelayout.pick_font(flat, qs, slots, samples, os.path.join(current_app.static_folder, 'fonts'))
    page = draft_page(n, quizscan_raw(qs, numbers))
    page.update(size=qs['size'], slots=slots, font=font, checked=checked,
                qs=[{k: p.get(k) for k in ('id', 'type', 'box', 'choices', 'text', 'number')} for p in qs['problems']])
    return page


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


def clean_box(box):
    """{'left', 'top', 'right', 'bottom'} as fractions of the page, the right way round
    and at least a sliver big; the whole page when it can't be read."""
    if isinstance(box, str):
        parts = box.split(',')
        box = dict(zip(('left', 'top', 'right', 'bottom'), parts)) if len(parts) == 4 else {}
    box = box if isinstance(box, dict) else {}
    l, t = _num(box.get('left'), 0.0), _num(box.get('top'), 0.0)
    r, b = _num(box.get('right'), 1.0), _num(box.get('bottom'), 1.0)
    l, r = min(l, r), max(l, r)
    t, b = min(t, b), max(t, b)
    if r - l < 0.02 or b - t < 0.02:
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

def item_problem(item, picture_files=()):
    """(qtype, title, question, answer, options) for a draft item, as the problem it would
    become. picture_files: its pictures (a stand-in name is enough for checking)."""
    paper = item.get('kind') == 'paper'
    use_page = item.get('use_page') and not paper
    qtype = 'paper' if paper else item.get('qtype') if item.get('qtype') in QTYPES else 'numeric'
    question = item.get('page_question') if use_page else item.get('question')
    answer = item.get('page_answer') if use_page else item.get('answer')
    choices = item.get('page_choices') if use_page and item.get('page_choices') else item.get('choices')
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


# ---------------------------------------------------------------- the review form

def _f(form, key, default=''):
    return form.get(key, default)


def update_from_form(data, form):
    """Take the review page's fields into the draft (only pages that were read)."""
    #(the names as the page showed them, so a title left as shown keeps following the workbook's name)
    if any(p.get('state') == 'done' for p in data.get('pages') or []):
        apply_names(data)
    data['name'] = _f(form, 'name', data.get('name', '')).strip()[:128]
    data['folder'] = ' '.join(_f(form, 'folder', data.get('folder', '')).split())
    for page in data['pages']:
        if page.get('state') != 'done':
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
        return S.create_subject(kind, want, parent)
    except S.ServiceError:
        return S.subject_named(kind, want)


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
            for item in page['items']:
                if not item.get('include'):
                    continue
                k += 1
                if item.get('title_auto', True):
                    item['title'] = '{}-{}'.format(quiz, k)[:64]
    return plan


def image_page(page):
    """A read page with no questions whose picture is kept: it becomes an Image only quiz of its
    own (the owner, 2026-10-19: "store it as a quiz instead of just storing the image")."""
    return page.get('state') == 'done' and page.get('kind') != 'problems' and any(p.get('keep') for p in page.get('pictures') or [])


def quiz_groups(data):
    """[(lead page, [pages])]: each problems page with something included is a quiz, unless
    it's joined to the one before; a page with no questions whose picture is kept is a quiz of its
    own (an Image only one)."""
    groups = []
    for page in data['pages']:
        if image_page(page):
            groups.append((page, [page]))
            continue
        if page.get('state') != 'done' or page.get('kind') != 'problems' or not any(i['include'] for i in page['items']):
            continue
        #(joined to the last quiz with problems: an Image only page between them isn't one, and
        #joining to it lost the page's problems; found by the tests, 2026-10-20)
        prev = next((g for g in reversed(groups) if not image_page(g[0])), None)
        if page.get('join_prev') and prev is not None:
            prev[1].append(page)
        else:
            groups.append((page, [page]))
    return groups


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
                errors = check_item(item, samples=0)['errors']
                if errors:
                    problems['page:{}:item:{}'.format(page['n'], i)] = errors
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
    with Image.open(page_file(job.id, page_n)) as im:
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
        from . import pagelayout
        with Image.open(page_file(job.id, page['n'])) as im:
            pic, _changed = pagelayout.erase_answers(im.convert('RGB'), page['slots'])
            pic, _changed = pagelayout.clean_answer_key(pic, {'problems': page.get('qs') or []}, page['slots'],
                                                       os.path.join(current_app.static_folder, 'fonts'))
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
            if check_item(item, samples=0)['errors']:
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
    fine. Returns {'quizzes': [VQuiz], 'problems': n, 'pictures': [file names]}."""
    from . import services as S
    book = _slug(data.get('name') or job.name)
    leads = lead_of(data)
    pictures, for_item, for_quiz, kept_of = [], {}, {}, {}
    #1. the pictures, cropped into the pictures folder
    for page in data['pages']:
        if page.get('state') != 'done':
            continue
        for pic in page.get('pictures', []):
            if not (pic.get('keep') or pic.get('use')):
                continue
            fname = save_picture(job, page['n'], pic['box'], '{}-p{}-{}'.format(book, page['n'], _slug(pic.get('label'))))
            pictures.append(fname)
            if pic.get('keep'):
                kept_of.setdefault(page['n'], []).append(fname)
            use = pic.get('use') or ''
            m = re.match(r'^item:(\d+):(\d+)$', use)
            if m:
                for_item.setdefault((int(m.group(1)), int(m.group(2))), []).append(fname)
            m = re.match(r'^quiz:(\d+)$', use)
            if m:
                for_quiz.setdefault(leads.get(int(m.group(1)), int(m.group(1))), []).append(fname)
    #2. the problems, and 3. one quiz per page (or joined pages)
    quizzes, made, reused, by_quiz = [], [], [], []
    #(the same problem twice, on a page or already in the library, is made once and used again:
    #the owner, 2026-10-18)
    by_key = {}
    for lead, pages in quiz_groups(data):
        ids, places = [], []
        if image_page(lead):
            #a page with no questions: an Image only quiz, its one problem the page's picture
            files = kept_of.get(lead['n'])[:1]
            vp = VProblem(author_id=author.id)
            errors = S.save_problem(vp, 'look', '{}-1'.format(lead['title'])[:64], '', '', {'markup': 'friendly', 'values': [],
                                    'images': [{'file': f, 'label': ''} for f in files]})
            if errors:
                raise ScanError('“{}” couldn’t be saved: {}'.format(lead['title'], ' '.join(errors)))
            made.append(vp.id)
            vq = VQuiz()
            errors = S.save_vquiz(vq, lead['title'], [vp.id], author_id=author.id, shuffle_order=False, calculator_ok=False)
            if errors:
                raise ScanError('The quiz “{}” couldn’t be saved: {}'.format(lead['title'], ' '.join(errors)))
            by_quiz.append([vp.id])
            quizzes.append(vq)
            continue
        for page in pages:
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
                vp = VProblem(author_id=author.id)
                errors = S.save_problem(vp, qtype, title, question, answer, options, page.get('calculator'))
                if errors:
                    raise ScanError('“{}” couldn’t be saved: {}'.format(title, ' '.join(errors)))
                by_key[key] = vp
                ids.append(vp.id)
                made.append(vp.id)
        vq = VQuiz()
        images = for_quiz.get(lead['n']) or []
        errors = S.save_vquiz(vq, lead['title'], ids, author_id=author.id, shuffle_order=bool(lead.get('shuffle')),
                              calculator_ok=bool(lead.get('calculator')), image=images[0] if images else None)
        if errors:
            raise ScanError('The quiz “{}” couldn’t be saved: {}'.format(lead['title'], ' '.join(errors)))
        by_quiz.append(list(dict.fromkeys(ids)))
        if all(page.get('slots') is not None for page in pages):
            vq.page_layout = page_layout_of(job, pages, places, ids, shuffled=bool(lead.get('shuffle')))
            vq.save()
        quizzes.append(vq)
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
