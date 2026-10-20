"""Scan workbook pages, with stand-ins for QuizScan (the page reader) and the Claude API
(no key, no cost). QuizScan reads each page; one more AI call gives its problems random
numbers (ai_helper.page_numbers); the page picture is then searched for answer places."""
import copy
import io
import json
import os
import sys
import types
from types import SimpleNamespace

import pytest

from app.qgen import ai_helper
from test_flow import app_db, login, no_titles  # noqa: F401  (fixture)


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
                return SimpleNamespace(get_final_message=lambda: msg)

            def __exit__(self, *a):
                return False
        return Running()


class QuizScanError(Exception):
    def __init__(self, message, fatal=False):
        super().__init__(message)
        self.fatal = fatal


def fake_quizscan(pages, error=None):
    """A stand-in for the quizscan package: convert_image answers with the next page in
    `pages` (or raises `error`); flat_page gives the page picture as saved."""
    mod = types.ModuleType('quizscan')
    mod.QuizScanError = QuizScanError
    mod.pages, mod.calls = list(pages), []

    def convert_image(path, api_key=None, model=None, client=None):
        mod.calls.append({'path': path, 'api_key': api_key, 'model': model})
        if error is not None:
            raise error
        return [copy.deepcopy(mod.pages.pop(0))]

    def flat_page(path, page):
        from PIL import Image
        with Image.open(path) as im:
            return im.copy()
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

    def use(pages=(), numbers=(), error=None, qs_error=None, checks=()):
        fake = FakeStreamClient(numbers, error, checks)
        qs = fake_quizscan(pages, qs_error)
        monkeypatch.setattr(ai_helper, '_client', lambda key: fake)
        monkeypatch.setitem(sys.modules, 'quizscan', qs)
        return SimpleNamespace(api=fake, qs=qs)
    use()
    yield use
    app.config['ANTHROPIC_API_KEY'] = None


def upload(client, files, name='Math Grade 2'):
    return client.post('/quiz/scan/new', data={'name': name, 'pages': files}, content_type='multipart/form-data')


def job_of(db):
    from app.qgen.models import ScanJob
    db.session.expire_all()
    return ScanJob.query.one()


def form_from(data, **changes):
    """The review form as the page sends it, from the draft, with the names the page shows
    (the workbook's: scan.apply_names) (changes: field name -> value, None to leave a check
    box unchecked)."""
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
    assert 'href="/quiz/scan"' not in html and '</svg> Scan workbook pages' not in html
    r = teacher.get('/quiz/scan')
    assert r.status_code == 302 and '/quiz/listvq' in r.headers['Location']
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    try:
        html = teacher.get('/quiz/listvq').data.decode()
        assert 'menu-disabled' not in html and '>Scan workbook pages</a>' in no_titles(html)
        assert '</svg> Scan workbook pages' in html
        assert '</svg> Scan workbook pages' in teacher.get('/quiz/listvp').data.decode()
        assert 'Upload and read' in teacher.get('/quiz/scan').data.decode()
        # students still don't get it, nor the menu item
        assert sam.get('/quiz/scan').status_code == 302
        assert 'Scan workbook pages' not in sam.get(sam.get('/quiz/scan').headers['Location']).data.decode()
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
    # QuizScan reads each page, from its private file, with the site's key
    assert [c['path'] for c in fakes.qs.calls] == [os.path.join(app.config['SCAN_DIR'], str(job.id), 'page-{}.jpg'.format(n))
                                                   for n in (1, 2, 3)]
    assert all(c['api_key'] == 'test-key' for c in fakes.qs.calls)
    # then one numbers call per page with problems (the picture page has none): text only, in
    # NUMBERS_SCHEMA, without the paper only problem
    assert len(fakes.api.calls) == 2
    sent = fakes.api.calls[0]['messages'][0]['content']
    assert isinstance(sent, str) and '"q1"' in sent and '"q3"' in sent and '"q4"' not in sent
    assert fakes.api.calls[0]['output_config']['format']['schema'] is ai_helper.NUMBERS_SCHEMA
    # two AI uses per page, logged like the other AI buttons
    calls = [c for c in AICall.query.filter_by(kind='scan', ok=True).all() if ': check' not in c.request]
    assert sorted(c.request for c in calls) == sorted(['Scan {} page {}'.format(job.id, n) for n in (1, 2, 3)]
                                                      + ['Scan {} page {}: numbers'.format(job.id, n) for n in (1, 2, 3)])

    # the draft
    page = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    # (quizzes named after the workbook: one per page, the picture page an Image only quiz)
    assert 'Page 1: Math Grade 2 1' in page and 'Page 2: Math Grade 2 2' in page and 'Picture only' in page
    assert 'It becomes an Image only quiz' in page
    assert 'Some versions have a negative answer' in page  # the take-away pool can go below zero
    assert 'Students get versions like:' in page
    assert 'Kept as on the page: Counts the apples in the picture.' in page
    assert '</svg> Paper only</span>' in page and 'The bottom is blurry.' in page
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

    # save: the farm goes at the top of page 1's quiz (and is its own Image only quiz too)
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(
        data, action='save', **dict(fixed, **{'p2-p1-use': 'quiz:1', 'p1-calculator': 'y'})))
    assert r.status_code == 302 and r.headers['Location'].endswith('/quiz/scan/done')
    done = teacher.get('/quiz/scan/done').data.decode()
    assert 'Made 3 quizzes from your pages, and 6 new problems for them' in done and 'Math Grade 2' in done
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
    # the scan and its files are gone
    assert ScanJob.query.count() == 0 and not os.path.exists(os.path.join(app.config['SCAN_DIR'], str(job.id)))


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
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, action='save', **{'p3-join_prev': 'y'}))
    assert r.status_code == 302
    in_quizzes = {i for vq in VQuiz.query.all() for i in json.loads(vq.vpid_lst)}
    doubles = [p for p in VProblem.query.all() if p.raw_prob == '[a] + [a] = ?']
    assert doubles and doubles[0].id in in_quizzes, 'page 3’s problem was not saved in any quiz'


def test_one_bad_item_saves_nothing(app_db, ai):
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz, ScanJob
    ai([QS_TIMES], [NUM_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    data = json.loads(job.data)
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, action='save', **{'p1i0-answer': '2 * zz'}))
    assert r.status_code == 400 and 'Nothing was saved yet' in r.data.decode() and 'zz' in r.data.decode()
    assert VProblem.query.count() == 0 and VQuiz.query.count() == 0
    # the edit was kept in the draft, and unchecking the item leaves nothing to save
    assert json.loads(job_of(db).data)['pages'][0]['items'][0]['answer'] == '2 * zz'
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, action='save', **{'p1i0-include': None}))
    assert r.status_code == 400 and 'There’s nothing to save yet' in r.data.decode()
    assert VProblem.query.count() == 0 and VQuiz.query.count() == 0
    # Keep draft: the title typed is kept, and the scan shows as a kept draft
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, action='keep', **{'p1-title': 'Doubles to 20'}))
    assert r.status_code == 302
    kept = json.loads(job_of(db).data)
    assert kept['pages'][0]['title'] == 'Doubles to 20' and kept['kept_at']
    assert 'Draft kept.' in teacher.get(r.headers['Location']).data.decode()
    assert 'Math Grade 2' in teacher.get('/quiz/scan').data.decode()
    # another teacher can Discard it too
    jid = job_of(db).id
    add_teacher(db)
    r = login(app, 'lee').post('/quiz/scan/{}/discard'.format(jid))
    assert r.status_code == 302
    assert ScanJob.query.count() == 0 and not os.path.exists(os.path.join(app.config['SCAN_DIR'], str(jid)))
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
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, action='save', **{'p1i0-use_page': 'y'}))
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
    html = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    assert 'That photo is too blurry to read.' in html and 'Read the rest' in html
    assert AICall.query.filter_by(kind='scan', ok=False).count() == 1
    # QuizScan reads it, but the numbers call fails: left to read again, QuizScan's reading kept
    import anthropic
    fakes = ai([QS_TIMES], error=anthropic.APIConnectionError(request=None))
    assert teacher.post('/quiz/scan/{}/read'.format(job.id)).status_code == 302
    page = json.loads(job_of(db).data)['pages'][0]
    assert page['state'] == 'error' and 'Couldn' in page['error'] and page['qs_reading']['title'] == 'Doubles'
    assert len(fakes.qs.calls) == 1
    html = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    assert 'Couldn' in html and 'Read the rest' in html
    # Read the rest: only the numbers are asked for again (QuizScan's reading isn't paid for twice)
    fakes = ai([QS_TIMES], [NUM_TIMES])
    assert teacher.post('/quiz/scan/{}/read'.format(job.id)).status_code == 302
    page = json.loads(job_of(db).data)['pages'][0]
    assert page['state'] == 'done' and page['title'] == 'Doubles' and len(page['items']) == 1
    assert not fakes.qs.calls and len(fakes.api.calls) == 1
    assert 'Read the rest' not in teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    # the hourly limit: a page needs room for its two AI calls
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
    assert 'Resume' in teacher.get('/quiz/scan/{}'.format(second.id)).data.decode()
    # with room for two, it's read
    AICall.query.filter_by(kind='problem').limit(1).one().created = datetime(2000, 1, 1)
    db.session.commit()
    assert teacher.post('/quiz/scan/{}/read'.format(second.id)).status_code == 302
    db.session.expire_all()
    assert json.loads(db.session.get(ScanJob, second.id).data)['pages'][0]['state'] == 'done'
    assert len(fakes.qs.calls) == 1 and len(fakes.api.calls) == 1


def test_upload_checks(app_db, ai):
    app, db = app_db
    from app.qgen.models import ScanJob
    teacher = login(app, 'teach')
    r = upload(teacher, [(io.BytesIO(b'not a picture'), 'notes.txt')])
    assert r.status_code == 302 and ScanJob.query.count() == 0
    assert '“notes.txt” isn’t a photo or PDF' in teacher.get('/quiz/scan').data.decode()
    upload(teacher, [(pdf(31), 'big.pdf')])
    assert ScanJob.query.count() == 0 and 'more than 30 pages' in teacher.get('/quiz/scan').data.decode()
    upload(teacher, [])
    assert ScanJob.query.count() == 0
    # photos are turned upright and scaled down
    ai([QS_TIMES, QS_TIMES], [NUM_TIMES, NUM_TIMES])
    upload(teacher, [(picture((400, 300), fmt='JPEG', exif_rotate=True), 'side.jpg'), (picture((4000, 1000)), 'wide.png')])
    job = job_of(db)
    from PIL import Image
    with Image.open(os.path.join(app.config['SCAN_DIR'], str(job.id), 'page-1.jpg')) as im:
        assert im.size == (300, 400)
    with Image.open(os.path.join(app.config['SCAN_DIR'], str(job.id), 'page-2.jpg')) as im:
        assert max(im.size) == 1600


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
    # a deleted teacher's scans go too
    lee = add_teacher(db)
    login(app, 'lee').post('/quiz/scan/new', data={'name': 'x', 'pages': [(picture(), 'p.png')]}, content_type='multipart/form-data')
    jid = ScanJob.query.one().id
    teacher.post('/deluser/{}'.format(lee.id))
    db.session.expire_all()
    assert ScanJob.query.count() == 0 and not os.path.exists(os.path.join(app.config['SCAN_DIR'], str(jid)))
