"""Scan workbook pages, with a stand-in for the Claude API (no key, no cost)."""
import io
import json
import os
from types import SimpleNamespace

import pytest

from app.qgen import ai_helper
from test_flow import app_db, login, no_titles  # noqa: F401  (fixture)


class FakeStreamClient:
    """Answers each page like the Claude API would (streamed), one payload per call, in turn."""
    def __init__(self, payloads, error=None):
        self.payloads, self.error, self.calls = list(payloads), error, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self.stream))

    def stream(self, **kw):
        self.calls.append(kw)
        client = self

        class Running:
            def __enter__(self):
                if client.error:
                    raise client.error
                payload = client.payloads.pop(0)
                msg = SimpleNamespace(stop_reason='end_turn', usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
                                      content=[SimpleNamespace(type='text', text=json.dumps(payload))])
                return SimpleNamespace(get_final_message=lambda: msg)

            def __exit__(self, *a):
                return False
        return Running()


def value(name, kind='whole', **kw):
    v = {'name': name, 'kind': kind, 'min': None, 'max': None, 'step': None, 'places': None, 'nonzero': False,
         'items': None, 'pick_n': None, 'formula': None, 'im_min': None, 'im_max': None, 'different_from': []}
    v.update(kw)
    return v


def box(l, t, r, b):
    return {'left': l, 'top': t, 'right': r, 'bottom': b}


def item(**kw):
    it = {'kind': 'question', 'box': box(0.1, 0.1, 0.9, 0.2), 'picture_ids': [], 'qtype': 'numeric', 'title': 'Item',
          'question': '', 'values': [], 'answer': None, 'choices': None, 'combos': None, 'show_n': None,
          'case_sensitive': False, 'grading_notes': None, 'page_question': '', 'page_answer': None, 'page_choices': None,
          'fixed_reason': None, 'answer_whole': False, 'answer_nonnegative': False}
    it.update(kw)
    return it


PAGE_ADD = {
    'page_kind': 'problems', 'title': 'Adding and taking away', 'directions': 'Add or subtract.', 'notes': None,
    'pictures': [{'id': 'p1', 'box': box(0.1, 0.5, 0.5, 0.7), 'label': 'apples'}],
    'items': [
        item(title='Add', question='[a] + [b] = ?', values=[value('a', min='1', max='9'), value('b', min='1', max='9')],
             answer='a + b', page_question='3 + 4 = ?', page_answer='7', answer_whole=True, answer_nonnegative=True),
        item(title='Take away', question='[a] - [b] = ?', values=[value('a', min='1', max='9'), value('b', min='1', max='9')],
             answer='a - b', page_question='9 - 4 = ?', page_answer='5', answer_whole=True, answer_nonnegative=True),
        item(title='Apples', question='How many apples?', page_question='How many apples?', page_answer='5',
             fixed_reason='Counts the apples in the picture.', picture_ids=['p1']),
        item(kind='paper_only', title='Triangles', qtype='essay', question='Color the triangles red.',
             page_question='Color the triangles red.', box=box(0.5, 0.75, 0.95, 0.95)),
    ],
}
PAGE_PICTURE = {'page_kind': 'picture', 'title': 'On the farm', 'directions': None, 'notes': None,
                'pictures': [{'id': 'a', 'box': box(0.05, 0.05, 0.95, 0.9), 'label': 'farm'}], 'items': []}
PAGE_TIMES = {'page_kind': 'problems', 'title': 'Doubles', 'directions': None, 'notes': 'The bottom is blurry.', 'pictures': [],
              'items': [item(title='Double', question='[a] + [a] = ?', values=[value('a', min='1', max='10')], answer='2 * a',
                             page_question='6 + 6 = ?', page_answer='12')]}


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
    """The AI key set, and the API replaced by a fake: ai(payloads) sets what it answers."""
    app, db = app_db
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    holder = {}

    def use(payloads=(), error=None):
        holder['fake'] = FakeStreamClient(payloads, error)
        monkeypatch.setattr(ai_helper, '_client', lambda key: holder['fake'])
        return holder['fake']
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
    """The review form as the page sends it, from the draft (changes: field name -> value,
    None to leave a check box unchecked)."""
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


def test_teachers_only_and_needs_a_key(app_db):
    app, db = app_db
    teacher, sam = login(app, 'teach'), login(app, 'sam')
    assert sam.get('/quiz/scan').status_code == 302 and '/quiz/scan' not in sam.get('/quiz/scan').headers['Location']
    assert sam.post('/quiz/scan/new').status_code == 302
    # no key: no button, and the page sends you back
    assert 'Scan workbook pages' not in teacher.get('/quiz/listvq').data.decode()
    r = teacher.get('/quiz/scan')
    assert r.status_code == 302 and '/quiz/listvq' in r.headers['Location']
    app.config['ANTHROPIC_API_KEY'] = 'test-key'
    try:
        assert '📷 Scan workbook pages' in teacher.get('/quiz/listvq').data.decode()
        assert '📷 Scan workbook pages' in teacher.get('/quiz/listvp').data.decode()
        assert 'Upload and read' in teacher.get('/quiz/scan').data.decode()
    finally:
        app.config['ANTHROPIC_API_KEY'] = None


def test_upload_read_check_and_save(app_db, ai):
    app, db = app_db
    from app.qgen.models import AICall, VProblem, VQuiz, ScanJob
    fake = ai([PAGE_ADD, PAGE_PICTURE, PAGE_TIMES])
    teacher = login(app, 'teach')
    r = upload(teacher, [(picture(), 'page1.png'), (picture(fmt='JPEG'), 'page2.jpg'), (pdf(1), 'page3.pdf')])
    assert r.status_code == 302
    job = job_of(db)
    assert job.pages == 3 and job.status == 'ready' and job.name == 'Math Grade 2'
    # the pages are private, not in the pictures folder
    for n in (1, 2, 3):
        assert os.path.exists(os.path.join(app.config['SCAN_DIR'], str(job.id), 'page-{}.jpg'.format(n)))
    assert not any(f.startswith('page-') for f in os.listdir(app.config['STATIC_DIR']))
    # one AI call per page, each with the page picture, logged like the other AI buttons
    assert len(fake.calls) == 3
    sent = fake.calls[0]['messages'][0]['content']
    assert sent[0]['type'] == 'image' and sent[0]['source']['media_type'] == 'image/jpeg'
    assert fake.calls[0]['output_config']['format']['schema'] is ai_helper.SCAN_SCHEMA
    assert AICall.query.filter_by(kind='scan', ok=True).count() == 3

    # the draft
    page = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    assert 'Page 1: Adding and taking away' in page and 'Page 2: On the farm' in page and 'picture only' in page
    assert 'Some versions have a negative answer' in page  # the take-away pool can go below zero
    assert 'Students get versions like:' in page
    assert 'Kept as on the page: Counts the apples in the picture.' in page
    assert '✏️ Paper only' in page and 'The bottom is blurry.' in page
    assert 'built-in method' not in page  # a missing setting shows as empty, never as Python's own names
    assert 'data-for="p1i3-box"' in page and 'id="p1i3-box"' in page  # the paper item's print box is drawn
    assert teacher.get('/quiz/scan/{}/page/1'.format(job.id)).headers['Content-Type'] == 'image/jpeg'
    data = json.loads(job.data)
    assert data['pages'][0]['items'][2]['use_page'] is True and data['pages'][0]['items'][0]['use_page'] is False
    assert data['pages'][0]['pictures'][0]['use'] == 'item:1:2'  # the apples go with their question

    # nobody else's
    from app.user.models import User
    other = User(username='lee', is_admin=True)
    other.set_password('pw-for-tests')
    db.session.add(other)
    db.session.commit()
    lee = login(app, 'lee')
    assert lee.get('/quiz/scan/{}'.format(job.id)).status_code == 404
    assert lee.get('/quiz/scan/{}/page/1'.format(job.id)).status_code == 404
    assert lee.post('/quiz/scan/{}/discard'.format(job.id)).status_code == 404

    # "Check and show examples": fix the take-away pool (a is b plus something)
    fixed = {'p1i1-v0-name': 'b', 'p1i1-v0-kind': 'whole', 'p1i1-v0-min': '1', 'p1i1-v0-max': '9',
             'p1i1-v1-name': 'c', 'p1i1-v1-kind': 'whole', 'p1i1-v1-min': '0', 'p1i1-v1-max': '9',
             'p1i1-v2-name': 'a', 'p1i1-v2-kind': 'calc', 'p1i1-v2-formula': 'b + c', 'p1i1-v2-min': '', 'p1i1-v2-max': '',
             'p1i1-answer': 'c'}
    r = teacher.post('/quiz/scan/{}/check'.format(job.id), data=form_from(data, page='1', item='1', **fixed))
    html = r.get_json()['html']
    assert 'negative' not in html and 'Students get versions like:' in html

    # save: page 3 joins page 1's quiz, the farm goes at the top of the quiz
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(
        data, action='save', **dict(fixed, **{'p3-join_prev': 'y', 'p2-p1-use': 'quiz:1', 'p1-calculator': 'y'})))
    assert r.status_code == 302 and r.headers['Location'].endswith('/quiz/scan/done')
    done = teacher.get('/quiz/scan/done').data.decode()
    assert 'Made 1 quiz and 5 problems' in done and 'Math Grade 2' in done
    vq = VQuiz.query.one()
    assert vq.title == 'Adding and taking away' and vq.shuffle_order is False and vq.calculator_ok
    probs = {p.id: p for p in VProblem.query.all()}
    order = [probs[i].title for i in json.loads(vq.vpid_lst)]
    assert order == ['Add', 'Take away', 'Apples', 'Triangles', 'Double']
    by = {p.title: p for p in probs.values()}
    static = app.config['STATIC_DIR']
    assert by['Triangles'].qtype == 'paper' and os.path.exists(os.path.join(static, by['Triangles'].image))
    assert by['Apples'].options['values'] == [] and by['Apples'].raw_prob == 'How many apples?' and by['Apples'].raw_ansr == '5'
    assert 'apples' in by['Apples'].image and os.path.exists(os.path.join(static, by['Apples'].image))
    assert by['Take away'].raw_ansr == 'c' and [v['name'] for v in by['Take away'].options['values']] == ['b', 'c', 'a']
    assert vq.image and 'farm' in vq.image and os.path.exists(os.path.join(static, vq.image))
    assert [g.title for g in vq.vqgroups] == ['Math Grade 2'] and all(p.vpgroups for p in probs.values())
    # the crop is the box's part of the page
    from PIL import Image
    with Image.open(os.path.join(static, by['Triangles'].image)) as im:
        assert abs(im.size[0] - 0.45 * 400) <= 2 and abs(im.size[1] - 0.2 * 600) <= 2
    # the scan and its files are gone
    assert ScanJob.query.count() == 0 and not os.path.exists(os.path.join(app.config['SCAN_DIR'], str(job.id)))


def test_one_bad_item_saves_nothing(app_db, ai):
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz
    ai([PAGE_TIMES])
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
    assert r.status_code == 400 and 'nothing to save yet' in r.data.decode()
    # Keep draft, then Discard
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, action='keep', **{'p1-title': 'Doubles to 20'}))
    assert r.status_code == 302 and json.loads(job_of(db).data)['pages'][0]['title'] == 'Doubles to 20'
    assert 'Doubles to 20' in teacher.get('/quiz/scan').data.decode() or 'Math Grade 2' in teacher.get('/quiz/scan').data.decode()
    jid = job_of(db).id
    assert teacher.post('/quiz/scan/{}/discard'.format(jid)).status_code == 302
    from app.qgen.models import ScanJob
    assert ScanJob.query.count() == 0 and not os.path.exists(os.path.join(app.config['SCAN_DIR'], str(jid)))


def test_paper_only_page_number_switch_saves_fixed_values(app_db, ai):
    app, db = app_db
    from app.qgen.models import VProblem
    ai([PAGE_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    data = json.loads(job.data)
    r = teacher.post('/quiz/scan/{}'.format(job.id), data=form_from(data, action='save', **{'p1i0-use_page': 'y'}))
    assert r.status_code == 302
    vp = VProblem.query.one()
    assert vp.raw_prob == '6 + 6 = ?' and vp.raw_ansr == '12' and vp.options['values'] == []


def test_errors_limits_and_retry(app_db, ai):
    app, db = app_db
    from app.qgen.models import AICall
    teacher = login(app, 'teach')
    # an AI error leaves the page to read again
    import anthropic
    ai(error=anthropic.APIConnectionError(request=None))
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    assert json.loads(job.data)['pages'][0]['state'] == 'error'
    page = teacher.get('/quiz/scan/{}'.format(job.id)).data.decode()
    assert 'Couldn' in page and 'Read the rest' in page
    ai([PAGE_TIMES])
    assert teacher.post('/quiz/scan/{}/read'.format(job.id)).status_code == 302
    assert json.loads(job_of(db).data)['pages'][0]['state'] == 'done'
    # the hourly limit counts each page
    from datetime import datetime
    from app.user.models import User
    teach = User.query.filter_by(username='teach').one()
    for _ in range(30):
        db.session.add(AICall(user_id=teach.id, created=datetime.now(), kind='problem', request='x', ok=True))
    db.session.commit()
    fake = ai([PAGE_TIMES])
    upload(teacher, [(picture(), 'q.png')], name='Second')
    from app.qgen.models import ScanJob
    second = ScanJob.query.filter_by(name='Second').one()
    page = json.loads(second.data)['pages'][0]
    assert page['state'] == 'waiting' and 'in the last hour' in page['error'] and not fake.calls


def test_upload_checks(app_db, ai):
    app, db = app_db
    from app.qgen.models import ScanJob
    teacher = login(app, 'teach')
    r = upload(teacher, [(io.BytesIO(b'not a picture'), 'notes.txt')])
    assert r.status_code == 302 and ScanJob.query.count() == 0
    assert 'isn’t a photo or PDF' in teacher.get('/quiz/scan').data.decode()
    upload(teacher, [(pdf(31), 'big.pdf')])
    assert ScanJob.query.count() == 0 and 'more than 30 pages' in teacher.get('/quiz/scan').data.decode()
    upload(teacher, [])
    assert ScanJob.query.count() == 0
    # photos are turned upright and scaled down
    ai([PAGE_TIMES, PAGE_TIMES])
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
    from app.user.models import User
    ai([PAGE_TIMES, PAGE_TIMES])
    teacher = login(app, 'teach')
    upload(teacher, [(picture(), 'p.png')])
    job = job_of(db)
    job.updated_at = datetime.now() - timedelta(days=31)
    db.session.commit()
    assert scan.remove_old_jobs() == 1 and ScanJob.query.count() == 0
    # a deleted teacher's scans go too
    lee = User(username='lee', is_admin=True)
    lee.set_password('pw-for-tests')
    db.session.add(lee)
    db.session.commit()
    login(app, 'lee').post('/quiz/scan/new', data={'name': 'x', 'pages': [(picture(), 'p.png')]}, content_type='multipart/form-data')
    jid = ScanJob.query.one().id
    teacher.post('/deluser/{}'.format(lee.id))
    db.session.expire_all()
    assert ScanJob.query.count() == 0 and not os.path.exists(os.path.join(app.config['SCAN_DIR'], str(jid)))
