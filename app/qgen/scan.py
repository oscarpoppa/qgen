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


def load_pages(files):
    """Uploaded files (photos and PDFs) -> page pictures: upright, RGB, long side at most
    LONG_SIDE. Raises ScanError for files that can't be read or too many pages."""
    from PIL import Image, ImageOps
    pages = []

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
            raise ScanError('“{}” isn’t a photo or PDF that can be read. Please use JPG, PNG or PDF.'.format(name))
        room()
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((LONG_SIDE, LONG_SIDE))
        pages.append(im)
    if not pages:
        raise ScanError('Please choose at least one photo or PDF of a workbook page.')
    return pages


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
    claimed = ScanJob.query.filter(ScanJob.id == job.id, db.or_(ScanJob.status != 'reading', ScanJob.updated_at < now - STALE)) \
        .update({'status': 'reading', 'updated_at': now, 'data': json.dumps(data)}, synchronize_session=False)
    db.session.commit()
    if not claimed:
        return False
    app = current_app._get_current_object()
    if app.testing:
        _read_all(app, job.id, api_key, user_id)  # tests wait for it
    else:
        threading.Thread(target=_read_all, args=(app, job.id, api_key, user_id), daemon=True).start()
    return True


def _read_all(app, job_id, api_key, user_id):
    with app.app_context():
        try:
            while True:
                job = db.session.get(ScanJob, job_id)
                if job is None:
                    return  # discarded meanwhile
                data = get_data(job)
                page = next((p for p in data['pages'] if p['state'] in ('waiting', 'reading')), None)
                if page is None:
                    break
                page['state'] = 'reading'
                put_data(job, data)
                db.session.commit()
                result = read_one(job, page['n'], api_key, user_id)
                job = db.session.get(ScanJob, job_id)
                if job is None:
                    return
                data = get_data(job)
                data['pages'][page['n'] - 1] = result
                put_data(job, data)
                db.session.commit()
                if result.get('stop'):
                    #the hourly limit: the rest stay unread until the teacher asks again
                    break
            job = db.session.get(ScanJob, job_id)
            if job is not None:
                job.status = 'ready'
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


def read_one(job, n, api_key, user_id):
    """Read page n with the AI. Returns the page's draft, or {'state': 'error', ...}."""
    from app import tuning
    from . import ai_helper
    hourly = tuning.get('ai_hourly')
    since = datetime.now() - timedelta(hours=1)
    if AICall.query.filter(AICall.user_id == user_id, AICall.created >= since).count() >= hourly:
        return {'n': n, 'state': 'waiting', 'stop': True,
                'error': 'You’ve used the AI helper {} times in the last hour, so this page is waiting. '
                         'Press “Read the rest” in a while.'.format(hourly)}
    call = AICall(user_id=user_id, created=datetime.now(), kind='scan', request='Scan {} page {}'.format(job.id, n), ok=False)
    try:
        with open(page_file(job.id, n), 'rb') as fh:
            raw, usage = ai_helper.read_page(api_key, fh.read())
        call.ok = True
        call.input_tokens, call.output_tokens = usage['input_tokens'], usage['output_tokens']
        page = draft_page(n, raw)
    except ai_helper.AIError as exc:
        page = {'n': n, 'state': 'error', 'error': str(exc)}
    finally:
        db.session.add(call)
        db.session.commit()
        current_app.logger.info('scan {} page {} read by the AI (ok={}, tokens in/out {}/{})'.format(
            job.id, n, call.ok, call.input_tokens, call.output_tokens))
    return page


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
    ids = {}
    for i, pic in enumerate(raw.get('pictures') or []):
        pid = 'p{}'.format(i + 1)
        ids[str(pic.get('id') or '')] = pid
        page['pictures'].append({'id': pid, 'box': clean_box(pic.get('box')), 'label': str(pic.get('label') or '')[:64],
                                 'keep': kind != 'other', 'use': ''})
    if kind != 'problems':
        page['items'] = []
        if not page['pictures']:
            page['pictures'] = [{'id': 'p1', 'box': clean_box(None), 'label': page['title'], 'keep': kind == 'picture', 'use': ''}]
        return page
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
    data['name'] = _f(form, 'name', data.get('name', '')).strip()[:128]
    data['folder'] = ' '.join(_f(form, 'folder', data.get('folder', '')).split())
    for page in data['pages']:
        if page.get('state') != 'done':
            continue
        n = page['n']
        pre = 'p{}-'.format(n)
        if pre + 'shown' not in form:
            continue  # not on the page that was sent
        page['title'] = _f(form, pre + 'title', page['title']).strip()[:64]
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
            item['title'] = _f(form, ip + 'title', item['title']).strip()[:64]
            if item['kind'] == 'paper':
                item['question'] = item['page_question'] = _f(form, ip + 'question', item['question'])
                item['answer'] = _f(form, ip + 'answer', item['answer'])
                item['box'] = clean_box(_f(form, ip + 'box', ''))
                continue
            qtype = _f(form, ip + 'qtype', item['qtype'])
            item['qtype'] = qtype if qtype in QTYPES else item['qtype']
            item['use_page'] = bool(form.get(ip + 'use_page'))
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


def quiz_groups(data):
    """[(lead page, [pages])]: each problems page with something included is a quiz, unless
    it's joined to the one before."""
    groups = []
    for page in data['pages']:
        if page.get('state') != 'done' or page.get('kind') != 'problems' or not any(i['include'] for i in page['items']):
            continue
        if page.get('join_prev') and groups:
            groups[-1][1].append(page)
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
    for lead, pages in quiz_groups(data):
        if not (lead.get('title') or '').strip():
            problems['page:{}:title'.format(lead['n'])] = ['Please give the quiz a title.']
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
    return fname


def save_all(job, data, author):
    """Make the pictures, problems and quizzes. Call check_all first: this assumes the draft is
    fine. Returns {'quizzes': [VQuiz], 'problems': n, 'pictures': [file names]}."""
    from . import services as S
    book = _slug(data.get('name') or job.name)
    leads = lead_of(data)
    pictures, for_item, for_quiz = [], {}, {}
    #1. the pictures, cropped into the pictures folder
    for page in data['pages']:
        if page.get('state') != 'done':
            continue
        for pic in page.get('pictures', []):
            if not (pic.get('keep') or pic.get('use')):
                continue
            fname = save_picture(job, page['n'], pic['box'], '{}-p{}-{}'.format(book, page['n'], _slug(pic.get('label'))))
            pictures.append(fname)
            use = pic.get('use') or ''
            m = re.match(r'^item:(\d+):(\d+)$', use)
            if m:
                for_item.setdefault((int(m.group(1)), int(m.group(2))), []).append(fname)
            m = re.match(r'^quiz:(\d+)$', use)
            if m:
                for_quiz.setdefault(leads.get(int(m.group(1)), int(m.group(1))), []).append(fname)
    #2. the problems, and 3. one quiz per page (or joined pages)
    quizzes, made = [], []
    for lead, pages in quiz_groups(data):
        ids = []
        for page in pages:
            for i, item in enumerate(page['items']):
                if not item['include']:
                    continue
                files = list(for_item.get((page['n'], i), []))
                if item['kind'] == 'paper':
                    files = [save_picture(job, page['n'], item['box'], '{}-p{}-{}'.format(book, page['n'], _slug(item['title'])))] + files
                    pictures.append(files[0])
                qtype, title, question, answer, options = item_problem(item, files)
                vp = VProblem(author_id=author.id)
                errors = S.save_problem(vp, qtype, title, question, answer, options, page.get('calculator'))
                if errors:
                    raise ScanError('“{}” couldn’t be saved: {}'.format(title, ' '.join(errors)))
                ids.append(vp.id)
                made.append(vp.id)
        vq = VQuiz()
        images = for_quiz.get(lead['n']) or []
        errors = S.save_vquiz(vq, lead['title'], ids, author_id=author.id, shuffle_order=bool(lead.get('shuffle')),
                              calculator_ok=bool(lead.get('calculator')), image=images[0] if images else None)
        if errors:
            raise ScanError('The quiz “{}” couldn’t be saved: {}'.format(lead['title'], ' '.join(errors)))
        quizzes.append(vq)
    #4. filed in the workbook's folder
    folder = data.get('folder')
    if folder:
        if made:
            S.file_items('problems', made, S.subject_named('problems', folder))
        if quizzes:
            S.file_items('quizzes', [q.id for q in quizzes], S.subject_named('quizzes', folder))
    return {'quizzes': quizzes, 'problems': len(made), 'pictures': pictures}
