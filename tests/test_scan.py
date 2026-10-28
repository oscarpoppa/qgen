"""Scan workbook pages, with stand-ins for QuizScan (the page reader) and the Claude API
(no key, no cost). QuizScan reads each page; one more AI call gives its problems random
numbers (ai_helper.page_numbers); the page picture is then searched for answer places."""
import copy
import io
import json
import os
import re
import sys
import types
from types import SimpleNamespace

import pytest

from app.qgen import ai_helper
from test_flow import app_db, login, no_titles  # noqa: F401  (fixture)


class Final:
    """A finished stream: no events to read along the way (a real one has them, for the progress), then its message."""
    def __init__(self, msg):
        self.msg = msg

    def __iter__(self):
        return iter(())

    def get_final_message(self):
        return self.msg


class FakeStreamClient:
    """Answers each call like the Claude API would (streamed), one payload per call, in turn.
    The check of a page's answer places (ai_helper.check_places) answers from `checks` instead,
    "all good" when it runs out; those calls are kept apart, in `check_calls`."""
    def __init__(self, payloads, error=None, checks=()):
        self.payloads, self.error, self.calls = list(payloads), error, []
        self.checks, self.check_calls = list(checks), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self.stream))

    def stream(self, **kw):
        checking = kw['system'][0]['text'] == ai_helper.CHECK_PROMPT
        (self.check_calls if checking else self.calls).append(kw)
        client = self

        class Running:
            def __enter__(self):
                if client.error:
                    raise client.error
                if checking:
                    payload = client.checks.pop(0) if client.checks else {'all_good': True, 'fixes': []}
                else:
                    payload = client.payloads.pop(0)
                msg = SimpleNamespace(stop_reason='end_turn', usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
                                      content=[SimpleNamespace(type='text', text=json.dumps(payload))])
                return Final(msg)

            def __exit__(self, *a):
                return False
        return Running()


class QuizScanError(Exception):
    def __init__(self, message, fatal=False):
        super().__init__(message)
        self.fatal = fatal


class FakeQSClient:
    """The Claude client QuizScan is given (scan._quizscan_client): each call answers at once,
    with its tokens, as the real one would."""
    def __init__(self, key):
        self.key, self.calls = key, []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(kw)

        class Running:
            def __enter__(self):
                return self

            def get_final_message(self):
                return SimpleNamespace(usage=SimpleNamespace(input_tokens=2000, output_tokens=800))

            def __iter__(self):
                #(a real stream is a series of events, read for the page's progress: none here)
                return iter(())

            def __exit__(self, *a):
                return False
        return Running()


def fake_quizscan(pages, error=None):
    """A stand-in for the quizscan package: convert_image answers with the next page in
    `pages` (or raises `error`), making its Claude calls through the client it's given as
    QuizScan does (two for a photo: mod.photo); flat_page gives the page picture as saved
    (mod.flat_mark: a color painted on its top left corner, to tell it apart). Its images
    module is QuizScan's own (the files a scan takes). mod.during(path) runs while a page is
    read; mod.most_at_once counts the pages read at the same time."""
    import threading
    import quizscan.images as real_images
    mod = types.ModuleType('quizscan')
    mod.QuizScanError = QuizScanError
    mod.images = real_images
    mod.pages, mod.calls = list(pages), []
    mod.photo, mod.flat_mark, mod.during = False, None, None
    mod.at_once = mod.most_at_once = 0
    lock = threading.Lock()

    def ask(client, text):
        with client.messages.stream(messages=[{'role': 'user', 'content': [{'type': 'text', 'text': text}]}]) as running:
            if error is not None:
                raise error
            running.get_final_message()

    def convert_image(path, api_key=None, model=None, client=None, note=None):
        with lock:
            mod.calls.append({'path': path, 'api_key': api_key, 'model': model, 'note': note})
            mod.at_once += 1
            mod.most_at_once = max(mod.most_at_once, mod.at_once)
        try:
            if mod.during:
                mod.during(path)
            if mod.photo:
                ask(client, 'Here is the image. Is it a photo of a page, and where is the page?')
            ask(client, 'Here is the page. Turn it into the page format.')
            with lock:
                return [copy.deepcopy(mod.pages.pop(0))]
        finally:
            with lock:
                mod.at_once -= 1

    def flat_page(path, page):
        from PIL import Image, ImageDraw
        with Image.open(path) as im:
            out = im.convert('RGB')
        if mod.flat_mark:
            ImageDraw.Draw(out).rectangle((0, 0, out.size[0] // 10, out.size[1] // 10), fill=mod.flat_mark)
        return out
    mod.convert_image, mod.flat_page = convert_image, flat_page
    return mod


# ---------------------------------------------------------------- QuizScan's pages (its file format)

def box(l, t, r, b):
    return {'left': l, 'top': t, 'right': r, 'bottom': b}


def qs_problem(pid, number, qtype, text, question, answer, at, pictures=(), choices=None, directions=None, notes=None):
    return {'id': pid, 'number': number, 'type': qtype, 'directions': directions, 'text': text, 'question': question,
            'choices': choices, 'answer': answer, 'pictures': [dict(p, file=None) for p in pictures], 'notes': notes,
            'box': at, 'number_box': None}


def qs_page(kind, title, problems=(), pictures=(), directions=None, notes=None):
    return {'format': 1, 'source': 'page.jpg', 'page': 1, 'converted_at': '2026-10-20T09:00:00', 'model': 'test-model',
            'size': {'width': 400, 'height': 600}, 'straightened': None, 'flatness': None, 'page_image': None,
            'page_kind': kind, 'title': title, 'title_box': box(0.1, 0.02, 0.9, 0.06) if title else None,
            'directions': directions, 'directions_box': box(0.1, 0.06, 0.9, 0.09) if directions else None, 'notes': notes,
            'problems': list(problems), 'pictures': list(pictures), 'other_text': [{'text': 'Name ______', 'box': box(0.6, 0.0, 0.95, 0.02)}]}


APPLES = {'id': 'pic1', 'label': 'apples', 'role': 'question', 'box': box(0.1, 0.5, 0.5, 0.7)}
STAR = {'id': 'pic2', 'label': 'star', 'role': 'decoration', 'box': box(0.9, 0.9, 0.98, 0.98)}
QS_ADD = qs_page('quiz', 'Adding and taking away', directions='Add or subtract.', pictures=[APPLES, STAR], problems=[
    qs_problem('q1', '1.', 'numeric', '1. 3 + 4 = ____', '3 + 4 = ____', '7', box(0.1, 0.1, 0.9, 0.18)),
    qs_problem('q2', '2.', 'numeric', '2. 9 - 4 = ____', '9 - 4 = ____', '5', box(0.1, 0.2, 0.9, 0.28)),
    qs_problem('q3', '3.', 'numeric', '3. How many apples? ____', 'How many apples?', '5', box(0.1, 0.3, 0.9, 0.48),
               pictures=[{k: APPLES[k] for k in ('id', 'label', 'box')}]),
    qs_problem('q4', '4.', 'paper', '4. Color the triangles red.', 'Color the triangles red.', None, box(0.5, 0.75, 0.95, 0.95)),
])
QS_PICTURE = qs_page('picture', 'On the farm', pictures=[{'id': 'pic1', 'label': 'farm', 'role': 'question', 'box': box(0.05, 0.05, 0.95, 0.9)}])
QS_TIMES = qs_page('quiz', 'Doubles', notes='The bottom is blurry.', problems=[
    qs_problem('q1', '1.', 'numeric', '1. 6 + 6 = ____', '6 + 6 = ____', '12', box(0.1, 0.1, 0.9, 0.2))])


# ---------------------------------------------------------------- the AI's numbers (NUMBERS_SCHEMA)

def value(name, kind='whole', **kw):
    v = {'name': name, 'kind': kind, 'min': '', 'max': '', 'step': '', 'places': '', 'nonzero': False,
         'items': '', 'pick_n': '', 'formula': '', 'im_min': '', 'im_max': '', 'different_from': []}
    v.update(kw)
    return v


def number_item(pid, **kw):
    it = {'id': pid, 'qtype': 'numeric', 'title': 'Item', 'question': '', 'values': [], 'answer': None, 'choices': None,
          'combos': None, 'show_n': None, 'case_sensitive': False, 'grading_notes': None, 'page_question': '',
          'page_answer': None, 'page_choices': None, 'page_text': None, 'fixed_reason': None,
          'answer_whole': False, 'answer_nonnegative': False}
    it.update(kw)
    return it


NUM_ADD = {'items': [
    number_item('q1', title='Add', question='[a] + [b] = ?', values=[value('a', min='1', max='9'), value('b', min='1', max='9')],
                answer='a + b', page_question='3 + 4 = ?', page_answer='7', page_text='[a] + [b] =',
                answer_whole=True, answer_nonnegative=True),
    number_item('q2', title='Take away', question='[a] - [b] = ?', values=[value('a', min='1', max='9'), value('b', min='1', max='9')],
                answer='a - b', page_question='9 - 4 = ?', page_answer='5', page_text='[a] - [b] =',
                answer_whole=True, answer_nonnegative=True),
    number_item('q3', title='Apples', question='How many apples?', answer='5', page_question='How many apples?', page_answer='5',
                fixed_reason='Counts the apples in the picture.'),
]}
NUM_TIMES = {'items': [
    number_item('q1', title='Double', question='[a] + [a] = ?', values=[value('a', min='1', max='10')], answer='2 * a',
                page_question='6 + 6 = ?', page_answer='12', page_text='[a] + [a] =')]}


def picture(size=(400, 600), color='white', fmt='PNG', exif_rotate=False):
    from PIL import Image
    im = Image.new('RGB', size, color)
    buf = io.BytesIO()
    if exif_rotate:
        exif = im.getexif()
        exif[0x0112] = 6  # taken sideways
        im.save(buf, 'JPEG', exif=exif)
    else:
        im.save(buf, fmt)
    buf.seek(0)
    return buf


def pdf(pages):
    from PIL import Image
    buf = io.BytesIO()
    ims = [Image.new('RGB', (300, 400), 'white') for _ in range(pages)]
    ims[0].save(buf, 'PDF', save_all=True, append_images=ims[1:])
    buf.seek(0)
    return buf


@pytest.fixture
def ai(app_db, monkeypatch):
    """The AI key set, and QuizScan and the API replaced by fakes: ai(pages, numbers) sets what
    QuizScan reads (one page per call) and what the numbers call answers (one payload per call)."""
    app, db = app_db
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    #(one page at a time, so each fake answers the pages in order; the tests of pages read side
    #by side set more)
    app.config['SCAN_READ_AT_ONCE'] = 1
    from app.qgen import scan as SC

    def use(pages=(), numbers=(), error=None, qs_error=None, checks=()):
        fake = FakeStreamClient(numbers, error, checks)
        qs = fake_quizscan(pages, qs_error)
        qs_clients = []

        def qs_client(key):
            qs_clients.append(FakeQSClient(key))
            return qs_clients[-1]
        monkeypatch.setattr(ai_helper, '_client', lambda key: fake)
        monkeypatch.setattr(SC, '_quizscan_client', qs_client)
        monkeypatch.setitem(sys.modules, 'quizscan', qs)
        return SimpleNamespace(api=fake, qs=qs, qs_clients=qs_clients)
    use()
    yield use
    app.config['ANTHROPIC_API_KEY'] = None
    app.config.pop('SCAN_READ_AT_ONCE', None)


def upload(client, files, name='Math Grade 2'):
    return client.post('/quiz/scan/new', data={'name': name, 'pages': files}, content_type='multipart/form-data')


def job_of(db):
    from app.qgen.models import ScanJob
    db.session.expire_all()
    return ScanJob.query.one()


def generate_all(teacher, job_id, **changes):
    """Each page's Generate quiz in turn, as the teacher would press them (the owner, 2026-10-25: a
    workbook is made page by page): every page that leads its quiz (joined pages go with the one
    before), each from the draft as it is then. Returns the responses, in order; stops at one that
    isn't a redirect (an error page)."""
    from app import db
    from app.qgen.models import ScanJob
    from app.qgen import scan as SC
    out = []
    while True:
        job = db.session.get(ScanJob, job_id)
        db.session.refresh(job)
        if job.status == SC.TRASHED:
            return out
        data = json.loads(job.data)
        form = form_from(data, **changes)
        leads = SC.lead_of(SC.update_from_form(copy.deepcopy(data), form))
        todo = [n for n, lead in sorted(leads.items()) if n == lead
                and next(p for p in data['pages'] if p['n'] == n).get('state') == 'done']
        if not todo:
            return out
        r = teacher.post('/quiz/scan/{}'.format(job_id), data=dict(form, generate=str(todo[0])))
        out.append(r)
        if r.status_code != 302:
            return out


def form_from(data, placed=True, **changes):
    """The review form as the page sends it, from the draft, with the names the page shows
    (the workbook's: scan.apply_names) (changes: field name -> value, None to leave a check
    box unchecked; placed=False leaves problems whose place wasn't found unplaced)."""
    from app.qgen import scan as SC
    data = copy.deepcopy(data)
    if any(p['state'] == 'done' for p in data['pages']):
        SC.apply_names(data)
    form = {'name': data.get('name', ''), 'folder': data.get('folder', '')}
    for page in data['pages']:
        if page['state'] != 'done':
            continue
        pre = 'p{}-'.format(page['n'])
        form[pre + 'shown'] = '1'
        form[pre + 'title'] = page['title']
        #(each page's "Save" check box, checked unless kept back: the owner, 2026-10-22)
        if page.get('save') is not False:
            form[pre + 'save'] = 'y'
        for flag in ('join_prev', 'shuffle', 'calculator'):
            if page.get(flag):
                form[pre + flag] = 'y'
        for pic in page['pictures']:
            key = pre + pic['id'] + '-'
            b = pic['box']
            form[key + 'box'] = '{},{},{},{}'.format(b['left'], b['top'], b['right'], b['bottom'])
            form[key + 'label'] = pic['label']
            form[key + 'use'] = pic['use']
            if pic['keep']:
                form[key + 'keep'] = 'y'
        for i, it in enumerate(page['items']):
            ip = 'p{}i{}-'.format(page['n'], i)
            if it['include']:
                form[ip + 'include'] = 'y'
            form[ip + 'title'] = it['title']
            form[ip + 'question'] = it['question']
            form[ip + 'answer'] = it['answer']
            if it['kind'] == 'paper':
                b = it['box']
                form[ip + 'box'] = '{},{},{},{}'.format(b['left'], b['top'], b['right'], b['bottom'])
                continue
            form[ip + 'qtype'] = it['qtype']
            #its place on the page as the page shows it (the blue box); placed=True drags each one,
            #as a teacher would where the page's blank wasn't found (the owner, 2026-10-20)
            pl = SC.place_of(page, it)
            if pl:
                b = pl[0]
                form[ip + 'place'] = '{},{},{},{}'.format(b['left'], b['top'], b['right'], b['bottom'])
                form[ip + 'placed'] = '1' if (pl[1] or placed) else ''
            if it['use_page']:
                form[ip + 'use_page'] = 'y'
            for f in ('choices', 'page_question', 'page_answer', 'page_choices'):
                form[ip + f] = it[f]
            for k, v in enumerate(it['values']):
                vp = '{}v{}-'.format(ip, k)
                for f in ('name', 'kind', 'min', 'max', 'step', 'places', 'items', 'formula'):
                    form[vp + f] = v.get(f, '')
                form[vp + 'different_from'] = ', '.join(v.get('different_from', []))
    for k, v in changes.items():
        if v is None:
            form.pop(k, None)
        else:
            form[k] = v
    return form


def add_teacher(db, name='lee'):
    from app.user.models import User
    u = User(username=name, is_admin=True)
    u.set_password('pw-for-tests')
    db.session.add(u)
    db.session.commit()
    return u


def test_teachers_only_and_needs_a_key(app_db):
    app, db = app_db
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    assert sam.get('/quiz/scan').status_code == 302 and '/quiz/scan' not in sam.get('/quiz/scan').headers['Location']
    assert sam.post('/quiz/scan/new').status_code == 302
    # no key: the More menu shows it grayed out, with the reason; no buttons; the page sends you back
    html = teacher.get('/quiz/listvq').data.decode()
    assert '<span class="menu-disabled" aria-disabled="true" title="Needs an AI key' in html
    #(and the page's own button grayed, with the reason: the owner, 2026-10-25, To do 45)
    assert 'href="/quiz/scan"' not in html
    assert 'disabled title="Needs an AI key, which this site doesn’t have"><svg class="ico" aria-hidden="true"><use href="#i-camera"/></svg> Scan Workbook Pages</button>' in html
    r = teacher.get('/quiz/scan')
    assert r.status_code == 302 and '/quiz/listvq' in r.headers['Location']
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    try:
        html = teacher.get('/quiz/listvq').data.decode()
        assert 'menu-disabled' not in html and '>Scanner</a>' in no_titles(html)
        assert '</svg> Scan Workbook Pages' in html
        assert '</svg> Scan Workbook Pages' in teacher.get('/quiz/listvp').data.decode()
        assert 'Upload and Read' in teacher.get('/quiz/scan').data.decode()
        # students still don't get it, nor the menu item
        assert sam.get('/quiz/scan').status_code == 302
        assert 'Scan Workbook Pages' not in sam.get(sam.get('/quiz/scan').headers['Location']).data.decode()
    finally:
        app.config['ANTHROPIC_API_KEY'] = None


def test_upload_read_check_and_save(app_db, ai):
    app, db = app_db
    from app.qgen.models import AICall, VProblem, VQuiz, VPGroup, VQGroup, ScanJob
    fakes = ai([QS_ADD, QS_PICTURE, QS_TIMES], [NUM_ADD, NUM_TIMES])
    teacher = login(app, 'teach')
    r = upload(teacher, [(picture(), 'page1.png'), (picture(fmt='JPEG'), 'page2.jpg'), (pdf(1), 'page3.pdf')])
    assert r.status_code == 302
    job = job_of(db)
    assert job.pages == 3 and job.status == 'ready' and job.name == 'Math Grade 2'
    # the pages are private, not in the pictures folder
    for n in (1, 2, 3):
        assert os.path.exists(os.path.join(app.config['SCAN_DIR'], str(job.id), 'page-{}.jpg'.format(n)))
    assert not any(f.startswith('page-') for f in os.listdir(app.config['STATIC_DIR']))
    # QuizScan reads each page, from its private full-size file, with the site's key
    assert sorted(c['path'] for c in fakes.qs.calls) == [os.path.join(app.config['SCAN_DIR'], str(job.id), 'orig-{}.jpg'.format(n))
                                                         for n in (1, 2, 3)]
    assert [c.key for c in fakes.qs_clients] == ['test-key'] * 3
    # then one numbers call per page with problems (the picture page has none): text only, in
    # NUMBERS_SCHEMA, without the paper only problem
    assert len(fakes.api.calls) == 2
    sent = fakes.api.calls[0]['messages'][0]['content']
    assert isinstance(sent, str) and '"q1"' in sent and '"q3"' in sent and '"q4"' not in sent
    assert fakes.api.calls[0]['output_config']['format']['schema'] is ai_helper.NUMBERS_SCHEMA
    # two AI uses per page (a scan, not a photo: QuizScan's reading, then the numbers), logged
    # like the other AI buttons
    calls = [c for c in AICall.query.filter_by(kind='scan', ok=True).all() if ': check' not in c.request]
    assert sorted(c.request for c in calls) == sorted(['Scan {} page {}: reading'.format(job.id, n) for n in (1, 2, 3)]
                                                      + ['Scan {} page {}: numbers'.format(job.id, n) for n in (1, 3)])

    # the draft
    page = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    # (quizzes named after the workbook: one per page, the picture page an Image only quiz)
    assert 'Page 1: Math Grade 2 1' in page and 'Page 2: Math Grade 2 2' in page and 'Picture only' in page
    assert 'It becomes an Image Only quiz' in page
    assert 'Some versions have a negative answer' in page  # the take-away pool can go below zero
    assert 'Students get versions like:' in page
    assert 'Kept as on the page: Counts the apples in the picture.' in page
    assert '</svg> Paper Only</span>' in page and 'The bottom is blurry.' in page
    assert 'Directions on the page: Add or subtract.' in page
    assert 'built-in method' not in page  # a missing setting shows as empty, never as Python's own names
    assert 'data-for="p1i3-box"' in page and 'id="p1i3-box"' in page  # the paper item's print box is drawn
    assert teacher.get('/quiz/scan/{}/page/1'.format(job.id)).headers['Content-Type'] == 'image/jpeg'
    data = json.loads(job.data)
    p1 = data['pages'][0]
    assert [it['qs_id'] for it in p1['items']] == ['q1', 'q2', 'q3', 'q4'] and p1['items'][3]['kind'] == 'paper'
    assert p1['items'][2]['use_page'] is True and p1['items'][0]['use_page'] is False
    assert p1['items'][0]['page_text'] == '[a] + [b] =' and p1['items'][0]['page_question'] == '3 + 4 = ?'
    # (the question picture only: the decoration is left out) the apples go with their question
    assert [p['label'] for p in p1['pictures']] == ['apples'] and p1['pictures'][0]['use'] == 'item:1:2'
    assert p1['size'] == {'width': 400, 'height': 600} and isinstance(p1['slots'], dict) and p1['font']
    assert data['pages'][1]['kind'] == 'picture' and data['pages'][1]['items'] == []

    # every teacher can open another's scan (students can't)
    add_teacher(db)
    lee = login(app, 'lee')
    assert lee.get('/quiz/scan/{}'.format(job.id)).status_code == 200
    assert lee.get('/quiz/scan/{}/page/1'.format(job.id)).status_code == 200
    sam = login(app, 'sam')
    assert sam.get('/quiz/scan/{}'.format(job.id)).status_code == 302
    assert sam.get('/quiz/scan/{}/page/1'.format(job.id)).status_code == 302
    assert sam.post('/quiz/scan/{}/discard'.format(job.id)).status_code == 302 and ScanJob.query.count() == 1

    # "Check and show examples": fix the take-away pool (a is b plus something)
    fixed = {'p1i1-v0-name': 'b', 'p1i1-v0-kind': 'whole', 'p1i1-v0-min': '1', 'p1i1-v0-max': '9',
             'p1i1-v1-name': 'c', 'p1i1-v1-kind': 'whole', 'p1i1-v1-min': '0', 'p1i1-v1-max': '9',
             'p1i1-v2-name': 'a', 'p1i1-v2-kind': 'calc', 'p1i1-v2-formula': 'b + c', 'p1i1-v2-min': '', 'p1i1-v2-max': '',
             'p1i1-answer': 'c'}
    r = teacher.post('/quiz/scan/{}/check'.format(job.id), data=form_from(data, page='1', item='1', **fixed))
    html = r.get_json()['html']
    assert 'negative' not in html and 'Students get versions like:' in html

    # generate each page (the owner, 2026-10-25): the farm goes at the top of page 1's quiz (and is its
    # own Image only quiz too); the last one sends the workbook to the Trash
    rs = generate_all(teacher, job.id, **dict(fixed, **{'p2-p1-use': 'quiz:1', 'p1-calculator': 'y'}))
    assert [r.status_code for r in rs] == [302, 302, 302] and rs[-1].headers['Location'].endswith('/quiz/scan')
    done = teacher.get('/quiz/scan').data.decode()
    assert 'Every page of “Math Grade 2” is made, so it went to the' in done
    quizzes = {q.title: q for q in VQuiz.query.all()}
    assert sorted(quizzes) == ['Math Grade 2 1', 'Math Grade 2 2', 'Math Grade 2 3']
    vq = quizzes['Math Grade 2 1']
    assert vq.shuffle_order is False and vq.calculator_ok
    probs = {p.id: p for p in VProblem.query.all()}
    order = [probs[i] for i in json.loads(vq.vpid_lst)]
    assert [p.title for p in order] == ['Math Grade 2 1-1', 'Math Grade 2 1-2', 'Math Grade 2 1-3', 'Math Grade 2 1-4']
    add, take, apples, triangles = order
    static = app.config['STATIC_DIR']
    assert add.raw_prob == '[a] + [b] = ?' and add.options.get('page_text') == '[a] + [b] ='
    assert triangles.qtype == 'paper' and os.path.exists(os.path.join(static, triangles.image))
    assert apples.options['values'] == [] and apples.raw_prob == 'How many apples?' and apples.raw_ansr == '5'
    assert 'apples' in apples.image and os.path.exists(os.path.join(static, apples.image))
    assert take.raw_ansr == 'c' and [v['name'] for v in take.options['values']] == ['b', 'c', 'a']
    assert vq.image and 'farm' in vq.image and os.path.exists(os.path.join(static, vq.image))
    # the quiz is taken on the page itself
    layout = vq.page_layout
    assert layout and len(layout['pages']) == 1 and os.path.exists(os.path.join(static, layout['pages'][0]['image']))
    assert layout['pages'][0]['items'] == ['q1', 'q2', 'q3', 'q4']
    # the picture page: an Image only quiz of the whole page
    farm = quizzes['Math Grade 2 2']
    look = [probs[i] for i in json.loads(farm.vpid_lst)]
    assert [p.qtype for p in look] == ['look'] and 'farm' in look[0].options['images'][0]['file']
    # page 3: a quiz of its own
    assert [probs[i].raw_prob for i in json.loads(quizzes['Math Grade 2 3'].vpid_lst)] == ['[a] + [a] = ?']
    # filed under the workbook's name: its quizzes in a Quizzes folder, its problems in a
    # Problems folder with one folder in it per quiz
    assert all([g.title for g in q.vqgroups] == ['Math Grade 2'] for q in quizzes.values())
    top = VPGroup.query.filter_by(title='Math Grade 2').one()
    for p in order:
        assert [g.title for g in p.vpgroups] == ['Math Grade 2 1'] and p.vpgroups[0].parent_id == top.id
    assert VQGroup.query.count() == 1
    # the crop is the box's part of the page
    from PIL import Image
    with Image.open(os.path.join(static, triangles.image)) as im:
        assert abs(im.size[0] - 0.45 * 400) <= 2 and abs(im.size[1] - 0.2 * 600) <= 2
    # the scan is in the Trash, its pages kept so it can be viewed or restored
    from app.qgen import scan as SC
    assert ScanJob.query.one().status == SC.TRASHED and os.path.exists(os.path.join(app.config['SCAN_DIR'], str(job.id)))


def test_joined_across_a_picture_page_keeps_its_problems(app_db, ai):
    """Page 3 "Join with the page before" when page 2 is a picture page: its problems go in a
    quiz, never lost."""
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz
    ai([QS_ADD, QS_PICTURE, QS_TIMES], [NUM_ADD, NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'page1.png'), (picture(), 'page2.png'), (picture(), 'page3.png')])
    job = job_of(db)
    data = json.loads(job.data)
    rs = generate_all(teacher, job.id, **{'p3-join_prev': 'y'})
    assert rs and all(r.status_code == 302 for r in rs)
    in_quizzes = {i for vq in VQuiz.query.all() for i in json.loads(vq.vpid_lst)}
    doubles = [p for p in VProblem.query.all() if p.raw_prob == '[a] + [a] = ?']
    assert doubles and doubles[0].id in in_quizzes, 'page 3’s problem was not saved in any quiz'


def test_pages_kept_back_stay_stashed_and_the_rest_are_saved(app_db, ai):
    """Each page made on its own (the owner, 2026-10-25): Generate quiz on page 1 makes only its quiz; the
    workbook stays open with page 2 still to make, and making that one sends the workbook to the Trash."""
    app, db = app_db
    from app.qgen.models import VQuiz, ScanJob
    from app.qgen import scan as SC
    ai([QS_ADD, QS_TIMES], [NUM_ADD, NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'page1.png'), (picture(), 'page2.png')])
    job = job_of(db)
    data = json.loads(job.data)
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=dict(form_from(data), generate='1'))
    assert r.status_code == 302 and r.headers['Location'].split('#')[0].endswith('/quiz/scan/{}'.format(job.id))
    assert VQuiz.query.count() == 1
    left = db.session.get(ScanJob, job.id)
    db.session.refresh(left)
    kept = json.loads(left.data)
    assert left.status != SC.TRASHED and [p['state'] for p in kept['pages']] == ['saved', 'done']
    assert 'Made the quiz “' in teacher.get(r.headers['Location']).data.decode()
    # page 2 later: its quiz, and the workbook goes to the Trash
    rs = generate_all(teacher, job.id)
    assert len(rs) == 1 and rs[0].status_code == 302 and VQuiz.query.count() == 2
    db.session.refresh(left)
    assert left.status == SC.TRASHED


def test_one_bad_item_saves_nothing(app_db, ai):
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz, ScanJob
    ai([QS_TIMES], [NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    data = json.loads(job.data)
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, generate='1', **{'p1i0-answer': '2 * zz'}))
    assert r.status_code == 400 and 'Nothing was saved yet' in r.data.decode() and 'zz' in r.data.decode()
    assert VProblem.query.count() == 0 and VQuiz.query.count() == 0
    # the edit was kept in the draft, and unchecking the item leaves nothing to save
    assert json.loads(job_of(db).data)['pages'][0]['items'][0]['answer'] == '2 * zz'
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, generate='1', **{'p1i0-include': None}), follow_redirects=True)
    assert 'Page 1 has nothing to make into a quiz yet: check at least one of its problems.' in r.data.decode()
    assert VProblem.query.count() == 0 and VQuiz.query.count() == 0
    # Stash draft (it was Keep draft: the owner, 2026-10-21): the title typed is kept, the scan is
    # stashed, and it's back on Scan workbook pages, in Stashed scans
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, action='keep', **{'p1-title': 'Doubles to 20'}))
    assert r.status_code == 302 and r.headers['Location'] == '/quiz/scan'
    kept = json.loads(job_of(db).data)
    assert kept['pages'][0]['title'] == 'Doubles to 20' and kept['kept_at'] and kept['put_away']
    page = teacher.get(r.headers['Location']).data.decode()
    assert '“{}” stashed, with your edits.'.format(job_of(db).name) in page
    assert 'Math Grade 2' in page and 'Stashed Workbooks' in page
    # another teacher can move it to the Trash too (the owner, 2026-10-25: Discard became Move to Trash)
    jid = job_of(db).id
    add_teacher(db)
    r = login(app, 'lee').post('/quiz/scan/{}/discard'.format(jid))
    assert r.status_code == 302
    from app.qgen import scan as SC
    assert ScanJob.query.one().status == SC.TRASHED and os.path.exists(os.path.join(app.config['SCAN_DIR'], str(jid)))
    assert VProblem.query.count() == 0 and VQuiz.query.count() == 0


def test_paper_only_page_number_switch_saves_fixed_values(app_db, ai):
    """"Use the page’s numbers": every student gets the page's own numbers."""
    app, db = app_db
    from app.qgen.models import VProblem
    ai([QS_TIMES], [NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    data = json.loads(job.data)
    assert data['pages'][0]['items'][0]['use_page'] is False
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, generate='1', **{'p1i0-use_page': 'y'}))
    assert r.status_code == 302
    vp = VProblem.query.one()
    assert vp.raw_prob == '6 + 6 = ?' and vp.raw_ansr == '12' and vp.options['values'] == []
    assert 'page_text' not in vp.options


def test_errors_limits_and_retry(app_db, ai):
    app, db = app_db
    from app.qgen.models import AICall, ScanJob
    from app import tuning
    teacher = login(app, 'teach')
    # QuizScan can't read the page: it's left to read again, with QuizScan's own words
    ai(qs_error=QuizScanError('That photo is too blurry to read.'))
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    page = json.loads(job.data)['pages'][0]
    assert page['state'] == 'error' and page['error'] == 'That photo is too blurry to read.'
    #(the Helper says it; its buttons are gone, the page's own "Read this page" does it: the owner, 2026-10-25)
    hints = teacher.post('/quiz/scan/{}/helper'.format(job.id)).get_json()['hints']
    assert any('That photo is too blurry to read.' in h['text'] and not h.get('actions') for h in hints)
    assert AICall.query.filter_by(kind='scan', ok=False).count() == 1
    # QuizScan reads it, but the numbers call fails: left to read again, QuizScan's reading kept
    import anthropic
    fakes = ai([QS_TIMES], error=anthropic.APIConnectionError(request=None))
    assert teacher.post('/quiz/scan/{}/read'.format(job.id)).status_code == 302
    page = json.loads(job_of(db).data)['pages'][0]
    assert page['state'] == 'error' and 'Couldn' in page['error'] and page['qs_reading']['title'] == 'Doubles'
    assert len(fakes.qs.calls) == 1
    hints = teacher.post('/quiz/scan/{}/helper'.format(job.id)).get_json()['hints']
    assert any('Couldn' in h['text'] for h in hints)
    # Read the rest: only the numbers are asked for again (QuizScan's reading isn't paid for twice)
    fakes = ai([QS_TIMES], [NUM_TIMES])
    assert teacher.post('/quiz/scan/{}/read'.format(job.id)).status_code == 302
    page = json.loads(job_of(db).data)['pages'][0]
    assert page['state'] == 'done' and page['title'] == 'Doubles' and len(page['items']) == 1
    assert not fakes.qs.calls and len(fakes.api.calls) == 1
    #(read now: the Helper says it's ready, with what to press; the owner, 2026-10-25)
    assert [h['text'] for h in teacher.post('/quiz/scan/{}/helper'.format(job.id)).get_json()['hints'] if h.get('key') == 'page-1'] \
        == ['Page 1 is ready: press “Generate Quiz”.']
    # the hourly limit: a page needs room for its three AI calls (QuizScan's photo check and
    # reading, then the numbers)
    from datetime import datetime
    from app.user.models import User
    teach = User.query.filter_by(username='teach').one()
    hourly = tuning.get('ai_hourly')
    used = AICall.query.filter_by(user_id=teach.id).count()
    for _ in range(hourly - 1 - used):
        db.session.add(AICall(user_id=teach.id, created=datetime.now(), kind='problem', request='x', ok=True))
    db.session.commit()
    fakes = ai([QS_TIMES], [NUM_TIMES])
    upload(teacher, [(picture(), 'q.png')], name='Second')
    second = ScanJob.query.filter_by(name='Second').one()
    page = json.loads(second.data)['pages'][0]
    assert page['state'] == 'waiting' and 'in the last hour' in page['error'] and not fakes.qs.calls and not fakes.api.calls
    #(the Helper says the page hasn't been read; the page's own card says why: the owner, 2026-10-25, CL2)
    assert any(h['text'] == 'Page 1 hasn’t been read yet. Press “Resume All”.' for h in teacher.post('/quiz/scan/{}/helper'.format(second.id)).get_json()['hints'])
    assert 'in the last hour' in teacher.get('/quiz/scan/{}'.format(second.id)).data.decode()
    # with room for two, it still waits; with room for three, it's read
    AICall.query.filter_by(kind='problem').limit(1).one().created = datetime(2000, 1, 1)
    db.session.commit()
    assert teacher.post('/quiz/scan/{}/read'.format(second.id)).status_code == 302
    db.session.expire_all()
    assert json.loads(db.session.get(ScanJob, second.id).data)['pages'][0]['state'] == 'waiting' and not fakes.qs.calls
    AICall.query.filter(AICall.kind == 'problem', AICall.created > datetime(2001, 1, 1)).limit(1).one().created = datetime(2000, 1, 1)
    db.session.commit()
    assert teacher.post('/quiz/scan/{}/read'.format(second.id)).status_code == 302
    db.session.expire_all()
    assert json.loads(db.session.get(ScanJob, second.id).data)['pages'][0]['state'] == 'done'
    assert len(fakes.qs.calls) == 1 and len(fakes.api.calls) == 1


def test_review_page_helper_choices_discard_page_and_button_words(app_db, ai):
    """The review page's Helper names the pages that didn't make it with Try again / Keep as it is / Discard page;
    Discard takes just that page out and numbers the rest on; Save says Generate quiz(zes); the stash button says
    Stash draft in Current scans and Unstash draft in the stash (the owner, 2026-10-23)."""
    app, db = app_db
    from app.qgen import scan as SC
    from app.qgen.models import ScanJob
    teacher = login(app, 'teach')
    ai([QS_TIMES] * 2, [NUM_TIMES] * 2)
    upload(teacher, [(picture(), 'p{}.png'.format(i)) for i in (1, 2)])
    job = job_of(db)
    #(page 2 did not make it)
    data = json.loads(job.data)
    data['pages'][1] = {'n': 2, 'state': 'error', 'error': 'This page took longer than 10 minutes to read, so it was stopped.'}
    job.data = json.dumps(data)
    db.session.commit()
    page = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    #(one Generate quiz per page: the owner, 2026-10-25)
    assert '>Generate Quiz</button>' in page and 'Generate quiz(zes)' not in page and '>Save</button>' not in page
    assert 'value="keep"' in page and 'Stash Draft' in page and 'Unstash Draft' not in page
    assert 'id="helper"' in page and 'js/helper.js' in page
    hints = teacher.post('/quiz/scan/{}/helper'.format(job.id)).get_json()['hints']
    mine = [h for h in hints if h.get('key') == 'page-2'][0]
    assert 'Page 2 didn’t make it: This page took longer than 10 minutes' in mine['text']
    #(the Helper only says it: Read this page and Discard page are on the page's own card, the owner 2026-10-25)
    assert not mine.get('actions')
    card = page[page.index('id="scan-page-2"'):]
    assert '>Read This Page</button>' in card and '/quiz/scan/{}/page/2/drop'.format(job.id) in card
    #(every page not generated has the trash icon and its state's badge: the owner, 2026-10-25)
    assert 'aria-label="Take page 1 out"' in page and 'Take page 2 out of “' in page
    assert 'class="scan-head-state scan-strip-error"' in card and 'class="scan-head-state scan-strip-' in page.split('id="scan-page-1"')[1]
    #(a page not read yet hasn't failed: the owner, 2026-10-23)
    data['pages'].append({'n': 3, 'state': 'waiting', 'error': SC.PAUSED_NOTE})
    waiting = SC.helper_hints(job, data, {'again': lambda n: '/a/{}'.format(n), 'drop': lambda n: '/d/{}'.format(n)})
    assert 'Page 3 hasn’t been read yet. Press “Resume All”.' in [h['text'] for h in waiting]
    #(in the stash: Unstash draft)
    SC.put_away(job)
    db.session.commit()
    stashed = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    assert 'Unstash Draft' in stashed and 'value="unstash"' in stashed and 'value="keep"' not in stashed
    # Discard page: just that page goes
    r = teacher.post('/quiz/scan/{}/page/2/drop'.format(job.id))
    assert r.status_code == 302
    db.session.expire_all()
    left = json.loads(db.session.get(ScanJob, job.id).data)['pages']
    assert [p['n'] for p in left] == [1] and left[0]['state'] == 'done'
    # a page that was read can be taken out too (the owner, 2026-10-25): the last one, and the workbook is gone
    r = teacher.post('/quiz/scan/{}/page/1/drop'.format(job.id))
    assert r.status_code == 302 and db.session.get(ScanJob, job.id) is None


def test_the_stash_has_folders(app_db, ai):
    """Real folders for stashed scans (the owner, 2026-10-23): shared by teachers, seen only on Scan workbook pages;
    a scan goes in one (none: Uncategorized); deleting a folder moves what's in it up a level."""
    app, db = app_db
    from app.qgen import scan as SC
    from app.qgen.models import ScanFolder, ScanJob
    teacher = login(app, 'teach')
    ai([QS_TIMES], [NUM_TIMES])
    upload(teacher, [(picture(), 'p.png')], name='Workbook A')
    job = job_of(db)
    SC.put_away(job)
    db.session.commit()
    page = teacher.get('/quiz/scan').data.decode()
    assert 'Stashed Workbooks' in page and 'Workbook A' in page and 'id="stash-new"' in page and 'Uncategorized' in page
    # the stashed workbook keeps its controls: continue, take out, move to Trash
    assert 'aria-label="Continue"' in page and 'aria-label="Take out"' in page and 'aria-label="Move to Trash"' in page
    # make a folder, then one inside it
    assert teacher.post('/quiz/scan/folders/new', data={'name': 'Fractions'}).status_code == 302
    top = ScanFolder.query.filter_by(name='Fractions').one()
    teacher.post('/quiz/scan/folders/new', data={'name': 'Grade 2', 'parent': top.id})
    inner = ScanFolder.query.filter_by(name='Grade 2').one()
    assert inner.parent_id == top.id
    # the same name twice at one level is refused, with why
    r = teacher.post('/quiz/scan/folders/new', data={'name': 'fractions'}, follow_redirects=True).data.decode()
    assert 'There’s already a folder called' in r
    # move the scan into the inner folder: it shows there, and in the folder around it, not in Uncategorized
    teacher.post('/quiz/scan/{}/move'.format(job.id), data={'to': inner.id})
    db.session.expire_all()
    assert db.session.get(ScanJob, job.id).folder_id == inner.id
    assert 'Workbook A' in teacher.get('/quiz/scan?stash={}'.format(top.id)).data.decode()
    assert 'Workbook A' in teacher.get('/quiz/scan?stash={}'.format(inner.id)).data.decode()
    assert 'Workbook A' not in teacher.get('/quiz/scan?stash=main').data.decode().split('id="scan-away"')[1]
    # rename; delete the outer folder: the inner one and the scan move up (the scan stays in the inner folder)
    teacher.post('/quiz/scan/folders/{}/rename'.format(top.id), data={'name': 'Maths'})
    assert ScanFolder.query.get(top.id).name == 'Maths'
    teacher.post('/quiz/scan/folders/{}/delete'.format(top.id))
    db.session.expire_all()
    assert ScanFolder.query.get(top.id) is None and ScanFolder.query.get(inner.id).parent_id is None
    assert db.session.get(ScanJob, job.id).folder_id == inner.id
    # delete the inner one: the scan is Uncategorized again
    teacher.post('/quiz/scan/folders/{}/delete'.format(inner.id))
    db.session.expire_all()
    assert db.session.get(ScanJob, job.id).folder_id is None
    # a folder that isn't there
    assert teacher.post('/quiz/scan/{}/move'.format(job.id), data={'to': 9999}).status_code == 404


def test_upload_checks(app_db, ai):
    app, db = app_db
    from app.qgen.models import ScanJob
    teacher = login(app, 'teach')
    r = upload(teacher, [(io.BytesIO(b'not a picture'), 'notes.txt')])
    assert r.status_code == 302 and ScanJob.query.count() == 0
    assert '“notes.txt” isn’t a picture that can be read.' in teacher.get('/quiz/scan').data.decode()
    upload(teacher, [(pdf(31), 'big.pdf')])
    assert ScanJob.query.count() == 0 and 'more than 30 pages' in teacher.get('/quiz/scan').data.decode()
    upload(teacher, [])
    assert ScanJob.query.count() == 0
    # photos are turned upright, kept full size for QuizScan, and scaled down to show
    ai([QS_TIMES, QS_TIMES], [NUM_TIMES, NUM_TIMES])
    upload(teacher, [(picture((400, 300), fmt='JPEG', exif_rotate=True), 'side.jpg'), (picture((4000, 1000)), 'wide.png')])
    job = job_of(db)
    from PIL import Image
    with Image.open(os.path.join(app.config['SCAN_DIR'], str(job.id), 'page-1.jpg')) as im:
        assert im.size == (300, 400)
    with Image.open(os.path.join(app.config['SCAN_DIR'], str(job.id), 'page-2.jpg')) as im:
        assert max(im.size) == 1600
    with Image.open(os.path.join(app.config['SCAN_DIR'], str(job.id), 'full-1.jpg')) as im:
        assert im.size == (300, 400)
    with Image.open(os.path.join(app.config['SCAN_DIR'], str(job.id), 'full-2.jpg')) as im:
        assert im.size == (4000, 1000)


def test_old_scans_and_deleted_users(app_db, ai):
    app, db = app_db
    from datetime import datetime, timedelta
    from app.qgen import scan
    from app.qgen.models import ScanJob
    ai([QS_TIMES, QS_TIMES], [NUM_TIMES, NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    job.updated_at = datetime.now() - timedelta(days=31)
    db.session.commit()
    assert scan.remove_old_jobs() == 1 and ScanJob.query.count() == 0
    # a deleted teacher's scans go to the teacher deleting the account, pages and all (the owner, 2026-10-20)
    from app.user.models import User
    lee = add_teacher(db)
    login(app, 'lee').post('/quiz/scan/new', data={'name': 'x', 'pages': [(picture(), 'p.png')]}, content_type='multipart/form-data')
    jid = ScanJob.query.one().id
    teacher.post('/deluser/{}'.format(lee.id))
    db.session.expire_all()
    job = ScanJob.query.one()
    assert job.id == jid and job.author_id == User.query.filter_by(username='teach').one().id
    assert os.path.exists(os.path.join(app.config['SCAN_DIR'], str(jid)))


def test_every_blank_needs_a_place_on_its_page(app_db, ai):
    """A scanned quiz has no ordinary questions (the owner, 2026-10-20): a problem whose blank
    wasn't found gets a dashed blue box at the end of its line and a red line; Save is grayed and
    refused until the box is dragged; the place dragged is kept, with the wording beside it."""
    app, db = app_db
    from app.qgen import scan as SC
    from app.qgen.models import VQuiz
    teacher = login(app, 'teach')
    ai([QS_TIMES], [NUM_TIMES])
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    data = json.loads(job.data)
    page = data['pages'][0]
    # nothing on the blank picture: a box just after the problem, dashed until it's dragged (the owner, 2026-10-25)
    assert page['slots']['q1'].get('guessed') and SC.place_of(page, page['items'][0])[1]
    assert 'crop crop-place is-guessed' in teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    # no box at all (no room beside it): it's missing
    page['slots'] = {}
    job.data = json.dumps(data)
    db.session.commit()
    assert SC.place_of(page, page['items'][0]) == ({'left': 0.7, 'top': 0.1, 'right': 0.9, 'bottom': 0.2}, False)
    assert SC.missing_places(data) == [(1, 0, '1.')]
    html = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    assert 'crop crop-place is-missing' in html and 'data-label="1."' in html and 'Where “1.” is answered' in html
    #(the page with something to fix starts open: the owner, 2026-10-25)
    assert 'id="scan-page-1" data-page="1" data-box="scan-page:1" data-fixed open data-keep-open' in html
    #(the red line says which box and where it goes, and a notice lists what's still to place: the
    #owner, 2026-10-22)
    no_place = 'No place on the page yet. On the page picture, drag its dashed box “1.” onto the circle or blank where the answer goes.'
    assert no_place in html
    #(no notice at the top any more: the Helper gives the steps; the owner, 2026-10-25)
    assert 'data-place-note' not in html
    steps = [h for h in teacher.post('/quiz/scan/{}/helper'.format(job.id)).get_json()['hints'] if h.get('key') == 'page-1'][0]
    assert steps['text'] == 'Page 1: 1 answer box to place' and steps['steps'] == [
        'Press “Place the Answer Boxes Again (Free)” under the page picture.',
        'Drag any dashed box that’s off onto where its answer goes.', 'Press “Generate Quiz”.']
    assert 'disabled title="Every problem needs its place on the page first (1.)"' in html
    # saving anyway is refused, with the red line once, and nothing is made
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, placed=False, generate='1'))
    assert r.status_code == 400 and r.data.decode().count(no_place) == 1 and not VQuiz.query.count()
    # left out: it needs no place
    assert not SC.missing_places(dict(data, pages=[dict(page, items=[dict(page['items'][0], include=False)])]))
    # dragged: kept by hand and saved on the page
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(
        data, placed=False, action='keep', **{'p1i0-place': '0.6,0.12,0.85,0.19', 'p1i0-placed': '1'}))
    slot = json.loads(job_of(db).data)['pages'][0]['slots']['q1']
    assert slot['answer'] == {'left': 0.6, 'top': 0.12, 'right': 0.85, 'bottom': 0.19} and slot['by_hand']
    # ...and kept as a test of the box finder: the page, and where the box was put (the owner, 2026-10-22)
    fixes = os.path.join(app.config['SCAN_DIR'], 'corrections')
    #(the newest one: other tests' scans can have the same number)
    kept = sorted((d for d in os.listdir(fixes) if d.startswith('{}-p1-'.format(job.id))),
                  key=lambda d: os.path.getmtime(os.path.join(fixes, d)))[-1:]
    assert len(kept) == 1 and os.path.exists(os.path.join(fixes, kept[0], 'page.jpg'))
    fixed = json.load(open(os.path.join(fixes, kept[0], 'page.json')))
    assert fixed['by_hand'] == ['q1'] and fixed['truth']['q1']['answer'] == slot['answer'] and fixed['problems']
    assert 'disabled title="Every problem needs its place' not in teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()


def test_a_save_that_fails_partway_leaves_nothing_behind(app_db, ai, monkeypatch):
    """A page's quiz fails after its problem was made: the problem is removed again, so pressing Generate
    quiz again doesn't make it twice (the code critic, 2026-10-20; one page at a time since 2026-10-25)."""
    app, db = app_db
    from app.qgen import services as S
    from app.qgen.models import VQuiz, VProblem
    teacher = login(app, 'teach')
    second = copy.deepcopy(QS_TIMES)
    second['title'] = 'Doubles again'
    ai([QS_TIMES, second], [NUM_TIMES, NUM_TIMES])
    upload(teacher, [(picture(), 'p1.png'), (picture(), 'p2.png')])
    job = job_of(db)
    data = json.loads(job.data)
    real = S.save_vquiz
    calls = []

    def flaky(vq, title, *a, **kw):
        calls.append(title)
        if len(calls) == 1:
            return ['Something went wrong.']
        return real(vq, title, *a, **kw)
    monkeypatch.setattr(S, 'save_vquiz', flaky)
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, generate='1', **{'p2i0-new': 'y'}))
    assert r.status_code == 400 and len(calls) == 1
    assert VQuiz.query.count() == 0 and VProblem.query.count() == 0
    # again, working: each made once
    monkeypatch.setattr(S, 'save_vquiz', real)
    rs = generate_all(teacher, job.id, **{'p2i0-new': 'y'})
    assert [r.status_code for r in rs] == [302, 302] and VQuiz.query.count() == 2 and VProblem.query.count() == 2


# ---------------------------------------------------------------- QuizScan's part (the owner, 2026-10-20)

def test_quizscan_reads_the_full_size_page_and_pictures_are_cut_from_it(app_db, ai):
    app, db = app_db
    from PIL import Image
    from app.qgen.models import AICall
    from app.qgen import scan as SC
    fakes = ai([QS_ADD], [NUM_ADD])
    fakes.qs.flat_mark = (0, 0, 255)
    teacher = login(app, 'teach')
    upload(teacher, [(picture((3000, 4000), fmt='JPEG'), 'big.jpg')])
    job = job_of(db)
    folder = os.path.join(app.config['SCAN_DIR'], str(job.id))
    # QuizScan reads the full-size page, not the smaller one shown
    # (the page as uploaded is kept, so it can be read again from the start)
    assert [c['path'] for c in fakes.qs.calls] == [os.path.join(folder, 'orig-1.jpg')]
    # its flat page is saved over both: full size, and scaled down to show and find places on
    with Image.open(os.path.join(folder, 'full-1.jpg')) as im:
        r, g, b = im.convert('RGB').getpixel((100, 100))
        assert im.size == (3000, 4000) and b > 200 and r < 60
    with Image.open(os.path.join(folder, 'page-1.jpg')) as im:
        r, g, b = im.convert('RGB').getpixel((40, 40))
        assert im.size == (1200, 1600) and b > 200 and r < 60
    page = json.loads(job.data)['pages'][0]
    assert page['state'] == 'done' and page['size'] == {'width': 1200, 'height': 1600}
    assert [q['id'] for q in page['qs']] == ['q1', 'q2', 'q3', 'q4']
    assert [it['qs_id'] for it in page['items']] == ['q1', 'q2', 'q3', 'q4']
    # pictures are cut from the full-size page
    name = SC.save_picture(job, 1, APPLES['box'], 'apples')
    with Image.open(os.path.join(app.config['STATIC_DIR'], name)) as im:
        assert im.size == (1200, 800)
    # QuizScan's call is logged on its own, with its tokens
    reading = AICall.query.filter_by(request='Scan {} page 1: reading'.format(job.id)).one()
    assert reading.ok and (reading.input_tokens, reading.output_tokens) == (2000, 800)


def test_a_photo_is_two_quizscan_calls(app_db, ai):
    app, db = app_db
    from app.qgen.models import AICall
    fakes = ai([QS_TIMES], [NUM_TIMES])
    fakes.qs.photo = True
    teacher = login(app, 'teach')
    upload(teacher, [(picture(fmt='JPEG'), 'photo.jpg')])
    job = job_of(db)
    calls = [c for c in AICall.query.filter_by(kind='scan').all() if ': check' not in c.request]
    assert sorted(c.request for c in calls) == ['Scan {} page 1: {}'.format(job.id, w) for w in ('numbers', 'photo check', 'reading')]
    assert all(c.ok for c in calls)


def test_any_kind_of_image(app_db, ai):
    app, db = app_db
    pytest.importorskip('cairosvg')
    from PIL import Image
    from app.qgen.models import ScanJob
    ai([QS_TIMES] * 10, [NUM_TIMES] * 10)
    teacher = login(app, 'teach')

    def tiff(n):
        buf = io.BytesIO()
        ims = [Image.new('RGB', (300, 400), 'white') for _ in range(n)]
        ims[0].save(buf, 'TIFF', save_all=True, append_images=ims[1:])
        buf.seek(0)
        return buf
    svg = io.BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400">'
                     b'<rect width="300" height="400" fill="white"/><text x="20" y="40">1. 2 + 2 = __</text></svg>')
    files = [(tiff(3), 'pages.tif'), (svg, 'page.svg')]
    try:
        import pillow_heif  # noqa: F401  (iPhone photos)
        heic = io.BytesIO()
        Image.new('RGB', (300, 400), 'white').save(heic, 'HEIF')
        heic.seek(0)
        files.append((heic, 'photo.heic'))
    except Exception:
        heic = None
    upload(teacher, files, name='Kinds')
    job = ScanJob.query.filter_by(name='Kinds').one()
    # a TIFF's pages are pages; an SVG drawing is drawn big enough to read
    assert job.pages == (5 if heic else 4)
    data = json.loads(job.data)
    assert all(p['state'] == 'done' for p in data['pages'])
    with Image.open(os.path.join(app.config['SCAN_DIR'], str(job.id), 'full-4.jpg')) as im:
        assert max(im.size) == 2400
    # a folder: what isn't a picture is skipped
    r = teacher.post('/quiz/scan/new', data={'name': 'Folder', 'from_folder': 'week 1', 'folder_pages': [
        (picture(), 'week 1/p1.png'), (io.BytesIO(b'remember the apples'), 'week 1/notes.txt'), (tiff(2), 'week 1/p2.tif')]},
        content_type='multipart/form-data', follow_redirects=True)
    assert 'Skipped 1 file in the folder' in r.data.decode()
    assert ScanJob.query.filter_by(name='Folder').one().pages == 3


@pytest.fixture
def own_connections(app_db, tmp_path):
    """A database where each thread gets its own connection, as on the site (the tests' own
    in-memory one is a single connection shared by every thread, so pages read side by side
    would mix up each other's queries there): a SQLite file, with the same people."""
    import sqlalchemy as sa
    app, db = app_db
    engines = db._app_engines[app]
    shared = engines[None]
    db.session.remove()
    engines[None] = sa.create_engine('sqlite:///{}'.format(tmp_path / 'scan.db'), connect_args={'timeout': 30, 'check_same_thread': False})
    try:
        db.create_all()
        from app.user.models import User
        for name, admin in (('teach', True), ('sam', False), ('kim', False)):
            u = User(username=name, is_admin=admin)
            u.set_password('pw-for-tests')
            db.session.add(u)
        db.session.commit()
        yield app, db
    finally:
        db.session.remove()
        engines[None].dispose()
        engines[None] = shared


def test_pages_are_read_three_at_once_and_pause_drops_them(own_connections, ai):
    app, db = own_connections
    import time
    from app.qgen import scan as SC
    from app.qgen.models import ScanJob
    #(enough for the three dropped pages to be read again on Resume)
    fakes = ai([QS_TIMES] * 15, [NUM_TIMES] * 15)
    app.config['SCAN_READ_AT_ONCE'] = 3
    started = []

    def during(path):
        started.append(path)
        if len(started) == 1:
            #Pause pressed while the first three are being read
            time.sleep(0.3)
            SC.pause_reading(ScanJob.query.one(), True)
        else:
            time.sleep(0.8)
    fakes.qs.during = during
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p{}.png'.format(i)) for i in range(1, 6)])
    job = job_of(db)
    data = json.loads(job.data)
    assert fakes.qs.most_at_once == 3
    # Pause (the owner, 2026-10-24): the pages being read when it was pressed finish and are kept; nothing
    # more starts; every page not read waits for Resume
    states = [p['state'] for p in data['pages']]
    assert states == ['done'] * 3 + ['waiting'] * 2, states
    assert data['pages'][3]['error'] == SC.PAUSED_NOTE and data.get('paused') and job.status == 'ready'
    # Resume reads the rest
    fakes.qs.during = None
    assert teacher.post('/quiz/scan/{}/read'.format(job.id)).status_code == 302
    assert [p['state'] for p in json.loads(job_of(db).data)['pages']] == ['done'] * 5


def test_a_page_over_its_time_limit_is_stopped_and_the_scan_goes_on(own_connections, ai):
    """A page whose reading runs over its time limit is marked with why and the scan goes on with the next
    pages (the owner, 2026-10-23); the scan is ready at the end, not stuck reading."""
    app, db = own_connections
    import time
    from app.qgen import scan as SC
    fakes = ai([QS_TIMES] * 3, [NUM_TIMES] * 3)
    app.config['SCAN_PAGE_MINUTES'] = 0.02   # 1.2 seconds
    started = []

    def during(path):
        started.append(path)
        if len(started) == 1:
            time.sleep(2.5)   # the first page takes far too long
    fakes.qs.during = during
    try:
        teacher = login(app, 'teach')
        upload(teacher, [(picture(), 'p{}.png'.format(i)) for i in range(1, 4)])
        time.sleep(3.0)   # (the page that ran over finishes unnoticed)
        job = job_of(db)
        data = json.loads(job.data)
        states = [p['state'] for p in data['pages']]
        assert states == ['error', 'done', 'done'], states
        assert data['pages'][0]['timed_out'] and 'longer than' in data['pages'][0]['error']
        assert job.status == 'ready'
    finally:
        app.config.pop('SCAN_PAGE_MINUTES', None)


def test_pages_side_by_side_keep_the_hourly_limit(own_connections, ai):
    app, db = own_connections
    from datetime import datetime
    from app import tuning
    from app.qgen.models import AICall
    from app.user.models import User
    fakes = ai([QS_TIMES] * 3, [NUM_TIMES] * 3)
    app.config['SCAN_READ_AT_ONCE'] = 3
    teacher = login(app, 'teach')
    teach = User.query.filter_by(username='teach').one()
    hourly = tuning.get('ai_hourly')
    #room for five calls: one page's three, not two pages'
    for _ in range(hourly - 5):
        db.session.add(AICall(user_id=teach.id, created=datetime.now(), kind='problem', request='x', ok=True))
    db.session.commit()
    upload(teacher, [(picture(), 'p{}.png'.format(i)) for i in range(1, 4)])
    pages = json.loads(job_of(db).data)['pages']
    assert fakes.qs.most_at_once == 1 and len(fakes.qs.calls) == 1
    assert pages[0]['state'] == 'done' and pages[1]['state'] == 'waiting' and 'in the last hour' in pages[1]['error']
    assert pages[2]['state'] == 'waiting'
    assert AICall.query.filter_by(user_id=teach.id).count() <= hourly


def test_quizscan_raw():
    from app.qgen.scan import quizscan_raw
    page = copy.deepcopy(QS_ADD)
    #(an empty problem with no place on the page: nothing to ask, left out)
    page['problems'].append(qs_problem('q5', '5.', 'numeric', '', '', None, None))
    raw = quizscan_raw(page, {'q1': NUM_ADD['items'][0]})
    assert raw['page_kind'] == 'problems' and raw['title'] == 'Adding and taking away'
    # a quiz page keeps only the pictures its questions use (not the decoration)
    assert [p['id'] for p in raw['pictures']] == ['pic1']
    assert [(it['qs_id'], it['kind']) for it in raw['items']] == [('q1', 'question'), ('q2', 'question'), ('q3', 'question'),
                                                                  ('q4', 'paper_only')]
    # the AI's numbers where it gave them, else the page's own wording, numbers kept
    assert raw['items'][0]['values'] and raw['items'][0]['box'] == page['problems'][0]['box']
    assert raw['items'][1]['fixed_reason'] == 'The AI didn’t return this one.' and raw['items'][1]['answer'] == '5'
    assert raw['items'][2]['picture_ids'] == ['pic1']
    assert quizscan_raw(QS_PICTURE, {})['page_kind'] == 'picture' and quizscan_raw(dict(QS_PICTURE, page_kind='cover'), {})['page_kind'] == 'other'


def test_read_a_page_again_with_a_note(app_db, ai):
    app, db = app_db
    from PIL import Image
    fakes = ai([QS_ADD, QS_TIMES], [NUM_ADD, NUM_TIMES])
    fakes.qs.flat_mark = (0, 0, 255)
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'page1.png'), (picture(), 'page2.png')])
    job = job_of(db)
    data = json.loads(job.data)
    assert [p['state'] for p in data['pages']] == ['done', 'done'] and not any(c['note'] for c in fakes.qs.calls)
    # the page shows the button, its note box and what it asks first
    html = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    assert 'Read This Page Again' in html and 'name="p1-again_note"' in html and 'Read page 1 again?' in html
    # page 1 read again with a note; the change made on page 2 meanwhile is kept
    fakes = ai([QS_ADD], [NUM_ADD])
    form = form_from(data, **{'p2-title': 'Doubles, changed', 'p1-again_note': '  Problem 6 is   missing. '})
    r = teacher.post('/quiz/scan/{}/page/1/again'.format(job.id), data=form)
    assert r.status_code == 302 and r.headers['Location'].endswith('/quiz/scan/{}'.format(job.id))
    folder = os.path.join(app.config['SCAN_DIR'], str(job.id))
    # QuizScan read the page as uploaded (not the straightened one), with the note
    assert fakes.qs.calls == [{'path': os.path.join(folder, 'orig-1.jpg'), 'api_key': None, 'model': fakes.qs.calls[0]['model'],
                               'note': 'Problem 6 is missing.'}]
    with Image.open(os.path.join(folder, 'orig-1.jpg')) as im:
        assert im.convert('RGB').getpixel((5, 5)) != (0, 0, 255) and max(im.convert('RGB').getpixel((5, 5))) > 200
    data = json.loads(job_of(db).data)
    assert data['pages'][0]['state'] == 'done' and data['pages'][0]['title'] == 'Adding and taking away'
    assert data['pages'][1]['title'] == 'Doubles, changed'
    # never while pages are being read
    from app.qgen.models import ScanJob
    from datetime import datetime
    j = job_of(db)
    j.status, j.updated_at = 'reading', datetime.now()
    db.session.commit()
    fakes = ai([QS_ADD], [NUM_ADD])
    teacher.post('/quiz/scan/{}/page/1/again'.format(job.id), data=form)
    assert not fakes.qs.calls


def test_read_again_drops_only_that_page():
    from app.qgen.scan import read_again, NOTE_LONGEST
    data = {'pages': [{'n': 1, 'state': 'done', 'title': 'a'}, {'n': 2, 'state': 'done', 'title': 'b', 'qs_reading': {}}]}
    read_again(data, 2, 'x' * 600)
    assert data['pages'][0] == {'n': 1, 'state': 'done', 'title': 'a'}
    assert data['pages'][1] == {'n': 2, 'state': 'waiting', 'note': 'x' * NOTE_LONGEST}
    assert read_again(data, 1, '   ')['pages'][0] == {'n': 1, 'state': 'waiting'}


def test_put_away_and_take_out(app_db, ai):
    app, db = app_db
    from app.qgen import scan as SC
    from app.qgen.models import ScanJob
    ai([QS_TIMES, QS_TIMES], [NUM_TIMES, NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p1.png')], name='Week 1')
    job = job_of(db)
    # a workbook read all the way can be stashed from its row too (the owner, 2026-10-25)
    html = teacher.get('/quiz/scan').data.decode()
    #("Put away" is "Stash" everywhere; the Stashed scans card is always there, empty with its note:
    #the owner 2026-10-21)
    assert 'Nothing stashed. Paused or stopped workbooks and drafts you stash wait here.' in html and 'Week 1' not in html.split('id="scan-away"')[1]
    assert '“Week 1” until you want it again' in html
    # Stash draft: the draft is stashed at once
    teacher.post('/quiz/scan/{}'.format(job.id), data=dict(form_from(json.loads(job.data)), action='keep'))
    assert json.loads(job_of(db).data).get('put_away')
    teacher.post('/quiz/scan/{}/take-out'.format(job.id))
    # taken out, a draft has a Stash button in Current scans
    html = teacher.get('/quiz/scan').data.decode()
    assert 'aria-label="Stash"' in html and 'Stash “Week 1” until you want it again: out of Current workbooks and the Dashboard' in html
    # stashed: out of Current scans and the Dashboard, into its own card
    assert teacher.post('/quiz/scan/{}/put-away'.format(job.id)).headers['Location'].endswith('/quiz/scan')
    html = teacher.get('/quiz/scan').data.decode()
    current, away = html.split('id="scan-away"')
    assert 'Week 1' not in current.split('id="scan-current"')[1] and 'No workbooks yet.' in current
    assert '<h2>Stashed Workbooks</h2>' in html and '<th>Stashed</th>' in away and 'Nothing stashed.' not in away
    assert 'Week 1' in away and 'Take “Week 1” out' in away and 'Continue: go on checking “Week 1”' in away
    # ...and never in the Dashboard's pop-over nor on its chip (the owner, 2026-10-21; it had a list
    # of its own there)
    pop = teacher.get('/quiz/scan/progress').get_json()
    assert 'Week 1' not in pop['html'] and 'scan-pop-away' not in pop['html'] and 'take-out' not in pop['html']
    assert 'Week 1' not in teacher.get('/dashboard').data.decode()
    # Take out still comes back to where it was asked from
    assert teacher.post('/quiz/scan/{}/take-out?back=dashboard'.format(job.id)).headers['Location'].endswith('/dashboard')
    teacher.post('/quiz/scan/{}/put-away'.format(job.id))
    # opened from there, it's as it was left
    assert 'Week 1' in teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    # taken out: back in Current scans
    teacher.post('/quiz/scan/{}/take-out'.format(job.id))
    html = teacher.get('/quiz/scan').data.decode()
    assert 'Nothing stashed.' in html and 'Week 1' in html.split('id="scan-current"')[1].split('id="scan-away"')[0]
    # a paused scan put away and resumed is back in Current scans, read the rest of the way
    data = json.loads(job_of(db).data)
    data['pages'].append({'n': 2, 'state': 'waiting', 'error': SC.PAUSED_NOTE})
    j = job_of(db)
    j.data, j.pages = json.dumps(dict(data, paused=True, kept_at=None)), 2
    import shutil
    folder = os.path.join(app.config['SCAN_DIR'], str(j.id))
    shutil.copy(os.path.join(folder, 'page-1.jpg'), os.path.join(folder, 'page-2.jpg'))
    db.session.commit()
    teacher.post('/quiz/scan/{}/put-away'.format(job.id))
    assert json.loads(job_of(db).data).get('put_away')
    assert teacher.post('/quiz/scan/{}/read?back=scans'.format(job.id)).headers['Location'].endswith('/quiz/scan')
    data = json.loads(job_of(db).data)
    assert not data.get('put_away') and [p['state'] for p in data['pages']] == ['done', 'done']
    # never while it's being read
    j = job_of(db)
    j.status, j.updated_at = 'reading', SC.datetime.now()
    db.session.commit()
    teacher.post('/quiz/scan/{}/put-away'.format(job.id))
    assert not json.loads(job_of(db).data).get('put_away') and ScanJob.query.count() == 1


def test_finished_notice_and_row_say_why_pages_didnt_make_it(app_db, ai):
    """The "scan finished" notice and the stopped scan's row say how many pages didn't make it and how many
    took too long (the owner, 2026-10-23)."""
    app, db = app_db
    from app.messages.models import Message
    from app.qgen import scan as SC
    teacher = login(app, 'teach')
    ai([QS_TIMES] * 3, [NUM_TIMES] * 3)
    upload(teacher, [(picture(), 'p{}.png'.format(i)) for i in (1, 2, 3)])
    job = job_of(db)
    data = json.loads(job.data)
    data['pages'][1] = {'n': 2, 'state': 'error', 'timed_out': True, 'error': 'too slow'}
    data['pages'][2] = {'n': 3, 'state': 'error', 'error': 'blurry'}
    job.data = json.dumps(data)
    db.session.commit()
    Message.query.delete()
    SC._tell_done(job)
    db.session.commit()
    body = Message.query.order_by(Message.id.desc()).first().body
    assert '1 of 3 pages are ready to check; 2 didn’t make it (1 took too long).' in body
    page = teacher.get('/quiz/scan').data.decode()
    assert 'Stopped: 2 pages didn’t make it (1 took too long)' in page


def test_the_dashboard_has_a_scanner_card_not_a_chip(app_db, ai):
    """The Dashboard's Scanner card (the owner, 2026-10-23): first, with its count; "No scans waiting." when
    empty, a row for each scan otherwise; no chip or pop-over."""
    app, db = app_db
    teacher = login(app, 'teach')
    html = teacher.get('/dashboard').data.decode()
    assert 'id="scan-card"' in html and '>Scanner</h2>' in html and '0 workbooks' in html and 'No workbooks waiting.' in html
    assert 'scan-chip"' not in html and 'id="scan-pop"' not in html
    assert html.index('id="scan-card"') < html.index('id="dash-right-now"') and 'id="scan-card" data-elastic="scanner" data-elastic-dir="v" data-box="scanner" data-url' in html
    ai([QS_TIMES], [NUM_TIMES])
    upload(teacher, [(picture(), 'p.png')])
    html = teacher.get('/dashboard').data.decode()
    assert '1 workbook<' in html and 'scan-progress-row' in html and 'No workbooks waiting.' not in html
    assert ' open' in html.split('id="scan-card"')[1].split('>')[0]
    #(the workbook's name opens its scan page, even while it's waiting or being read; a bar's moving part shows while reading)
    assert 'class="name-link scan-pop-name" href="/quiz/scan/{}"'.format(job_of(db).id) in html
    assert teacher.get('/quiz/scan/progress').get_json()['count'] == '1 workbook'


def test_stashed_scans_can_be_dragged_onto_folders(app_db, ai):
    """The stash's scans have drag handles and its folder list has drop places (static/js/scanstash.js), and the
    folder card has the vertical bar (static/js/splitter.js) (the owner, 2026-10-23)."""
    app, db = app_db
    from app.qgen import scan as SC
    teacher = login(app, 'teach')
    ai([QS_TIMES], [NUM_TIMES])
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    SC.put_away(job)
    teacher.post('/quiz/scan/folders/new', data={'name': 'Fractions'})
    html = teacher.get('/quiz/scan').data.decode()
    away = html.split('id="scan-away"')[1]
    assert 'tr data-stash-drag data-url="/quiz/scan/{}/move"'.format(job.id) in away
    assert 'data-stash-drop="all"' in away and 'data-stash-drop="main"' in away and re.search(r'data-stash-drop="\d+"', away)
    assert 'class="stash-split"' in away and 'js/splitter.js' in html


def _spread_photo():
    """A photo-like picture of two facing pages: paper on a desk, each side with ruled lines of ink, and a shadow
    down the spine in the middle, darkest at the fold."""
    import numpy as np
    from PIL import Image
    h, w = 800, 1000
    a = np.full((h, w), 214.0)                      # the desk
    a[120:700, 80:920] = 238.0                      # the two pages
    for x in range(480, 521):                       # the shadow: gradual, down the whole height of the pages
        a[120:700, x] -= 60 * (1 - abs(x - 500) / 20.0)
    for y in range(180, 640, 36):                   # lines of text on each page
        a[y:y + 6, 120:450] = 70
        a[y:y + 6, 560:880] = 70
    im = Image.fromarray(a.astype('uint8')).convert('RGB')
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=92)
    buf.seek(0)
    return buf


def test_a_photo_of_two_pages_becomes_two_scan_pages(app_db, ai):
    """A spread (two facing pages, a shadow down the spine) is cut at the spine into two pages, left then right,
    each marked as from one photo (the owner, 2026-10-23); a single page isn't touched."""
    app, db = app_db
    teacher = login(app, 'teach')
    ai([QS_TIMES] * 3, [NUM_TIMES] * 3)
    upload(teacher, [(_spread_photo(), 'spread.jpg'), (picture(), 'single.png')])
    data = json.loads(job_of(db).data)
    assert [p.get('spread', False) for p in data['pages']] == [True, True, False] and len(data['pages']) == 3
    from PIL import Image
    from app.qgen import scan as SC
    left, right = (Image.open(SC.full_file(job_of(db).id, n)) for n in (1, 2))
    assert 400 < left.width < 600 and 400 < right.width < 600 and left.width + right.width == 1000


def test_the_open_stash_folder_stays_open_when_the_page_redraws(app_db, ai):
    """The scans page redraws its cards now and then (while a scan is read, or when something changes) by asking for
    its own address: with ?stash=<folder> it must ask for that folder, or the list jumped back to All scans (the owner, 2026-10-23)."""
    app, db = app_db
    teacher = login(app, 'teach')
    html = teacher.get('/quiz/scan?stash=1').data.decode()
    assert "fetch(location.pathname + location.search" in html and "fetch(location.pathname, " not in html


def test_single_pages_are_never_cut_in_two(app_db):
    """A page that only looks like it could be two (a hard gray divider down the middle, a plain page, a soft shadow
    along only one edge) stays one page (the owner, 2026-10-23)."""
    import numpy as np
    from PIL import Image
    from app.qgen import spread
    h, w = 800, 1000
    plain = np.full((h, w), 238.0)
    for y in range(180, 640, 36):
        plain[y:y + 6, 120:880] = 70
    divider = plain.copy()
    divider[100:700, 497:503] = 120                      # a hard line, not a soft shadow
    edge = plain.copy()
    for x in range(0, 60):                               # shading along the left edge only
        edge[:, x] -= 60 * (1 - x / 60.0)
    for a in (plain, divider, edge):
        assert spread.find(Image.fromarray(a.astype('uint8')).convert('RGB')) is None


def test_the_stash_move_dialog_is_the_standard_folder_dialog(app_db, ai):
    """A scan's Move dialog is the standard folder picker (put-dialog, rows drawn when it opens), and its Uncategorized row
    ("top") moves a scan out of its folder (the owner, 2026-10-23)."""
    app, db = app_db
    from app.qgen.models import ScanFolder
    from app.qgen import scan as SC
    teacher = login(app, 'teach')
    ai([QS_TIMES], [NUM_TIMES])
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    SC.put_away(job)
    teacher.post('/quiz/scan/folders/new', data={'name': 'Fractions'})
    fid = ScanFolder.query.filter_by(name='Fractions').one().id
    html = teacher.get('/quiz/scan').data.decode()
    dialog = html.split('id="stash-move"')[1].split('</dialog>')[0]
    assert 'pick-dialog put-dialog' in html.split('id="stash-move"')[0].rsplit('<dialog', 1)[1] and 'data-folder-pick' in dialog
    assert '[[{}, "Fractions", 1, "folder"]]'.format(fid) in dialog.replace('\n', '')
    assert 'name="stay" value=""' in dialog and 'name="stay" value="{}"'.format(fid) in teacher.get('/quiz/scan?stash={}'.format(fid)).data.decode().split('id="stash-move"')[1]
    assert teacher.post('/quiz/scan/{}/move'.format(job.id), data={'to': str(fid)}).status_code == 302
    assert job_of(db).folder_id == fid
    assert teacher.post('/quiz/scan/{}/move'.format(job.id), data={'to': 'top'}).status_code == 302
    assert job_of(db).folder_id is None


def test_a_dragged_scan_leaves_the_view_where_it_was(app_db, ai):
    """Dragging a scan onto a folder sends 'stay' with the folder open now, and the page comes back to it, not to the
    folder the scan went to (the owner, 2026-10-23)."""
    app, db = app_db
    from app.qgen.models import ScanFolder
    from app.qgen import scan as SC
    teacher = login(app, 'teach')
    ai([QS_TIMES], [NUM_TIMES])
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    SC.put_away(job)
    teacher.post('/quiz/scan/folders/new', data={'name': 'A'})
    teacher.post('/quiz/scan/folders/new', data={'name': 'B'})
    a, b = (ScanFolder.query.filter_by(name=n).one().id for n in 'AB')
    teacher.post('/quiz/scan/{}/move'.format(job.id), data={'to': str(a)})
    r = teacher.post('/quiz/scan/{}/move'.format(job.id), data={'to': str(b), 'stay': str(a)})
    assert r.headers['Location'].endswith('/quiz/scan?stash={}#scan-away'.format(a)) and job_of(db).folder_id == b
    r = teacher.post('/quiz/scan/{}/move'.format(job.id), data={'to': '', 'stay': ''})
    assert r.headers['Location'].endswith('/quiz/scan#scan-away') and job_of(db).folder_id is None
    r = teacher.post('/quiz/scan/{}/move'.format(job.id), data={'to': str(a)})  # (the Move dialog: goes to where it went)
    assert r.headers['Location'].endswith('stash={}#scan-away'.format(a))


def test_the_continue_arrow_works_on_a_paused_scan_like_its_name(app_db, ai):
    """A paused scan's name and its Continue arrow both open the scan's page (the arrow was grayed out; the owner, 2026-10-23)."""
    app, db = app_db
    teacher = login(app, 'teach')
    ai([QS_TIMES], [NUM_TIMES])
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    html = teacher.get('/quiz/scan').data.decode()
    assert 'Paused' not in html or 'disabled title="Continue' not in html
    assert 'href="/quiz/scan/{}"'.format(job.id) in html and 'aria-label="Continue"' in html
    assert teacher.get('/quiz/scan/{}'.format(job.id)).status_code == 200


def test_stash_folders_move_into_each_other_and_the_list_is_the_standard_one(app_db, ai):
    """A stash folder can be moved inside another (or out to the top) from the open folder's Folder options menu, the
    list is drawn with the standard rows and Expand all / Collapse all, and a move that can't be done says why
    (the owner, 2026-10-23)."""
    app, db = app_db
    from app.qgen.models import ScanFolder
    teacher = login(app, 'teach')
    teacher.post('/quiz/scan/folders/new', data={'name': 'A'})
    a = ScanFolder.query.filter_by(name='A').one().id
    teacher.post('/quiz/scan/folders/new', data={'name': 'B', 'parent': str(a)})
    b = ScanFolder.query.filter_by(name='B').one().id
    teacher.post('/quiz/scan/folders/new', data={'name': 'C'})
    c = ScanFolder.query.filter_by(name='C').one().id
    html = teacher.get('/quiz/scan?stash={}'.format(a)).data.decode()
    away = html.split('id="scan-away"')[1]
    for needle in ('class="side-item"', 'class="side-fold"', 'class="side-row current', 'data-side-level="open"', 'data-side-level="close"', 'side-auto-first', 'data-stash-drop="{}"'.format(b)):
        assert needle in away, needle
    assert 'data-stash-dialog="stash-move-folder"' in away and 'id="stash-move-folder"' in away
    rows = away.split('id="stash-move-folder"')[1].split('data-pick-rows>')[1].split('</script>')[0]   # (the folder's own Move to: not itself, not what's in it)
    assert '"C"' in rows and '"A"' not in rows and '"B"' not in rows
    #(B moves out to the top, then A inside C; A can't go inside what's in it)
    assert teacher.post('/quiz/scan/folders/{}/move'.format(b), data={'to': 'top'}).status_code == 302
    assert db.session.get(ScanFolder, b).parent_id is None
    assert teacher.post('/quiz/scan/folders/{}/move'.format(a), data={'to': str(c)}).status_code == 302
    assert db.session.get(ScanFolder, a).parent_id == c
    r = teacher.post('/quiz/scan/folders/{}/move'.format(c), data={'to': str(a)})   # (C into A, which is inside C)
    assert r.status_code == 302 and db.session.get(ScanFolder, c).parent_id is None


def test_every_page_loads_the_whole_row_click_script(app_db):
    """The click-anywhere-on-a-row script (static/js/rowclick.js) is on every page, and the scanned quiz's boxes start from what the
    server sent (the owner, 2026-10-23)."""
    app, db = app_db
    teacher = login(app, 'teach')
    assert 'js/rowclick.js' in teacher.get('/quiz/listvq').data.decode()
    import os
    js = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'pagequiz.js')).read()
    assert 'el.value = el.defaultValue' in js


def test_restore_only_takes_a_workbook_out_of_the_trash(app_db, ai):
    """Restore on a workbook that isn't in the Trash changes nothing (the code critic, 2026-10-25): a stashed one
    keeps its folder."""
    app, db = app_db
    from app.qgen import scan as SC
    from app.qgen.models import ScanFolder
    ai([QS_TIMES], [NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    f = ScanFolder(name='Week 3')
    db.session.add(f)
    db.session.commit()
    SC.put_away(job)
    job.folder_id = f.id
    db.session.commit()
    assert teacher.post('/quiz/scan/{}/restore'.format(job.id)).status_code == 302
    job = job_of(db)
    assert job.folder_id == f.id and job.status != SC.TRASHED


def test_a_reading_that_breaks_leaves_a_trashed_workbook_in_the_trash(app_db, ai, monkeypatch):
    """The reading going wrong after the workbook was moved to the Trash doesn't bring it back, and no page is
    left "still with the AI" (the code critic, 2026-10-25)."""
    app, db = app_db
    from app.qgen import scan as SC
    from app.qgen.models import ScanJob
    ai([QS_TIMES], [NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png'), (picture(), 'q.png')])
    job = job_of(db)
    data = json.loads(job.data)
    data['pages'][1].update(state='waiting')
    data['out'] = {'2': ['old-run', '2026-10-25T10:00:00', 1]}
    job.data = json.dumps(data)
    db.session.commit()

    def broken(*a, **kw):
        j = db.session.get(ScanJob, job.id)
        j.status = SC.TRASHED
        db.session.commit()
        raise RuntimeError('the reading broke')
    monkeypatch.setattr(SC, 'still_out', broken)
    with app.test_request_context():
        SC.start_reading(job_of(db), 'test-key', ids_of('teach'))
    job = job_of(db)
    assert job.status == SC.TRASHED and 'out' not in json.loads(job.data)


def test_generate_keeps_a_page_stopped_meanwhile(app_db, ai):
    """A page stopped after the workbook page was loaded stays stopped when another page is generated from
    that page (the code critic, 2026-10-25)."""
    app, db = app_db
    from app.qgen import scan as SC
    ai([QS_TIMES, QS_TIMES], [NUM_TIMES, NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png'), (picture(), 'q.png')])
    job = job_of(db)
    loaded = json.loads(job.data)
    loaded['stopped'] = []   # (as the page was loaded: nothing stopped yet)
    with SC.page_lock(job.id) as data:
        data['stopped'] = [2]
    SC.mark_saved(job.id, loaded, [1], {'quizzes': []})
    assert json.loads(job_of(db).data)['stopped'] == [2]


def ids_of(name):
    from app.user.models import User
    return User.query.filter_by(username=name).one().id


def test_an_old_page_error_names_the_button_the_page_has(app_db, ai):
    """A page that failed before the buttons were renamed shows "Read this page", the button it has now, not
    "Read the rest" or "Try again" (the owner, 2026-10-25)."""
    app, db = app_db
    from app.qgen import scan as SC
    old = ('The AI’s answer for this page ran too long, so the page wasn’t read. Press “Read the rest” to try it again. '
           'If it stops again, photograph just this page, closer up, and scan that photo as a new scan.')
    assert 'Press “Read This Page” to read it again. If it stops again' in SC.shown_error(old)
    assert SC.shown_error('Press “Try again” on it in a while.') == 'Press “Read This Page” in a while.'
    ai([QS_TIMES, QS_TIMES], [NUM_TIMES, NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png'), (picture(), 'q.png')])
    job = job_of(db)
    data = json.loads(job.data)
    data['pages'][0] = {'n': 1, 'state': 'error', 'error': old}
    job.data = json.dumps(data)
    db.session.commit()
    page = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    hints = teacher.post('/quiz/scan/{}/helper'.format(job.id)).get_json()['hints']
    said_all = [page] + [h['text'] for h in hints] + [st for h in hints for st in h.get('steps') or []]
    for said in said_all:
        assert 'Read the rest' not in said and '“Try again”' not in said
    #(the Helper: the reason, short, and the next step naming today's buttons; the owner, 2026-10-25)
    mine = [h for h in hints if h.get('key') == 'page-1'][0]
    assert mine['text'] == 'Page 1 didn’t make it (the AI’s answer ran too long)'
    assert mine['steps'] == ['Press “Read This Page” to read it again (a few AI calls).']


def test_a_problem_with_no_blank_gets_a_box_right_after_it(app_db):
    """No blank printed after a problem ("3/4 + 1/5 ="): its answer box goes just to its right, as tall as it, stopping
    short of the next problem on the line, dashed ('guessed') until it's dragged (the owner, 2026-10-25)."""
    from app.qgen import scan as SC
    qs = [{'id': 'q1', 'box': {'left': 0.10, 'top': 0.12, 'right': 0.30, 'bottom': 0.16}},
          {'id': 'q2', 'box': {'left': 0.39, 'top': 0.12, 'right': 0.58, 'bottom': 0.16}},
          {'id': 'q3', 'box': {'left': 0.66, 'top': 0.12, 'right': 0.85, 'bottom': 0.17}},
          {'id': 'q4', 'box': {'left': 0.10, 'top': 0.20, 'right': 0.30, 'bottom': 0.24}}]
    found = {'q4': {'kind': 'field', 'answer': {'left': 0.31, 'top': 0.2, 'right': 0.4, 'bottom': 0.24}, 'text': None, 'char': 0.02}}
    slots = SC.guess_places(qs, dict(found), covered={'q2'})
    a1, a2, a3 = (slots[k]['answer'] for k in ('q1', 'q2', 'q3'))
    assert a1['left'] > 0.30 and a1['right'] < 0.39 and (a1['top'], a1['bottom']) == (0.12, 0.16)
    assert a2['right'] < 0.66 and a3['right'] <= 0.99
    assert all(slots[k]['guessed'] for k in ('q1', 'q2', 'q3')) and slots['q4'] == found['q4']   # (a found one stays)
    assert slots['q2']['text'] == qs[1]['box'] and slots['q1']['text'] is None   # (random numbers: its wording is written again)


def test_a_read_page_with_things_to_fix_shows_a_mark_not_a_check(app_db, ai):
    """A page that was read but isn't ready (answer boxes to place) shows "!" on its thumbnail, with what's left in
    its tooltip; ✓ only when it's ready (the owner, 2026-10-25)."""
    app, db = app_db
    ai([QS_TIMES], [NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    page = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    assert 'scan-strip-page scan-strip-done' in page and 'scan-strip-fix' not in page   # (its box was placed)
    data = json.loads(job.data)
    data['pages'][0]['slots'] = {}
    job.data = json.dumps(data)
    db.session.commit()
    page = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    assert 'scan-strip-page scan-strip-fix' in page and 'data-fix="; 1 answer box to place"' in page
    assert 'title="Page 1: read; 1 answer box to place. See page 1 full size"' in page and '<b>!</b>' in page


def test_choices_with_no_marks_found_get_no_typing_box(app_db):
    """A question with choices whose printed marks weren't found is asked in the list under the page, never in a guessed
    typing box: the box drew its whole choice list in big letters over the page (the owner, 2026-10-28, "superhero trivia")."""
    from app.qgen import scan as SC
    qs = [{'id': 'q1', 'type': 'choice_one', 'choices': ['a', 'b'], 'box': {'left': 0.1, 'top': 0.1, 'right': 0.4, 'bottom': 0.14}},
          {'id': 'q2', 'type': 'text', 'box': {'left': 0.1, 'top': 0.2, 'right': 0.4, 'bottom': 0.24}}]
    slots = SC.guess_places(qs, {})
    assert 'q1' not in slots and slots['q2']['kind'] == 'field'
    page = {'kind': 'problems', 'qs': qs, 'slots': slots}
    assert SC.place_of(page, {'kind': 'question', 'qs_id': 'q1', 'qtype': 'choice_one'}) is None
    assert SC.place_of(page, {'kind': 'question', 'qs_id': 'q2', 'qtype': 'text'})[1] is True


def test_a_pages_heading_says_what_kind_of_quiz_it_makes(app_db):
    """In everyday words, from the checked items (the owner, 2026-10-28)."""
    from app.qgen import scan as SC
    q = lambda t, inc=True, kind='question': {'qtype': t, 'include': inc, 'kind': kind}  # noqa: E731
    assert SC.kind_summary({'state': 'done', 'kind': 'problems', 'items': [q('choice_one')] * 16}) == 'Multiple choice'
    assert SC.kind_summary({'state': 'done', 'kind': 'problems', 'items': [q('choice_one')] * 12 + [q('text')] * 4
                            + [q('numeric', False)]}) == '12 multiple choice · 4 short answer'
    assert SC.kind_summary({'state': 'done', 'kind': 'problems', 'items': [q('numeric')] * 3 + [q('x', kind='paper')]}) \
        == '3 number · 1 on paper'
    assert SC.kind_summary({'state': 'done', 'kind': 'picture', 'items': []}) == 'Picture only'
    assert SC.kind_summary({'state': 'waiting', 'kind': 'problems', 'items': [q('text')]}) == ''


def test_a_pages_warning_is_yellow_and_in_the_helper(app_db, ai):
    """The reader's note on a page (e.g. a question printed with no number) is a yellow warning on the page, and the
    Helper has a yellow line for it (the owner, 2026-10-28)."""
    app, db = app_db
    ai([QS_TIMES], [NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    data = json.loads(job.data)
    data['pages'][0]['notes'] = 'One question is printed without a number.'
    job.data = json.dumps(data)
    db.session.commit()
    page = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    assert '<p class="hint hint-warn small">' in page and 'One question is printed without a number.' in page
    assert 'class="badge scan-kinds"' in page
    hints = teacher.post('/quiz/scan/{}/helper'.format(job.id)).get_json()['hints']
    assert {'level': 'warn', 'key': 'note-1', 'text': 'Page 1 has a warning: read it before you generate.'} in hints
