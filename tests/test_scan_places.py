"""A scanned page made level, its answer places found on its own lines, the AI's check of those
places (each move checked by the program), and the page's own labels ("1 a.") on the quiz
(the owner, 2026-10-20). No real AI: a fake client answers."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.qgen import ai_helper, pagelayout, scan
from test_flow import app_db, login  # noqa: F401  (fixture)
from test_scan import FakeStreamClient


def box(l, t, r, b):
    return {'left': l, 'top': t, 'right': r, 'bottom': b}


def sheet(slope=0.0, rows=8, size=(1000, 1300), edge=False):
    """A worksheet: two columns of "1 a.   6 x 7 = ____" rows, in print; the whole page then
    sloped (each row drops `slope` pixels per pixel across). Returns (image, QuizScan-like page
    with the boxes of the level page)."""
    from PIL import ImageFont
    W, H = size
    img = Image.new('RGB', size, 'white')
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=30)
    problems = []
    for r in range(rows):
        for c, x0 in enumerate((90, 560)):
            y = 200 + r * 120
            label = '{} {}.'.format(r + 1, 'ab'[c])
            d.text((x0, y), label, fill='black', font=font)
            d.text((x0 + 100, y), '{} x {} ='.format(r + 2, c + 3), fill='black', font=font)
            d.line([(x0 + 290, y + 34), (x0 + 400, y + 34)], fill='black', width=3)
            pid = 'q{}'.format(len(problems) + 1)
            problems.append({'id': pid, 'number': label, 'type': 'numeric',
                             'text': '{}  {} x {} = ____'.format(label, r + 2, c + 3), 'number_box': None,
                             'box': box(x0 / W, (y - 4) / H, (x0 + 410) / W, (y + 40) / H)})
    if slope:
        img = img.transform(size, Image.AFFINE, (1, 0, 0, -slope, 1, slope * W / 2), resample=Image.BICUBIC, fillcolor='white')
    if edge:
        ImageDraw.Draw(img).line([(4, 0), (9, H)], fill='black', width=4)
    return img, {'problems': problems, 'pictures': []}


def rows_slope(img):
    full = pagelayout.ink_mask(np.asarray(img.convert('L')))
    return np.degrees(pagelayout._skew(full))


# ---------------------------------------------------------------- leveling

def test_a_sloping_page_is_made_level_and_its_boxes_move_with_it():
    img, page = sheet(slope=0.012)
    assert rows_slope(img) > 0.3
    flat, moved = pagelayout.level_page(img, page)
    assert abs(rows_slope(flat)) < 0.1
    # the boxes still sit on their rows: each one holds its answer line
    slots = pagelayout.find_slots(flat, moved)
    assert len(slots) == len(page['problems'])


def test_a_level_page_is_left_exactly_as_it_is():
    img, page = sheet(slope=0.0)
    same, same_page = pagelayout.level_page(img, page)
    assert same is img and same_page is page


def test_a_dark_edge_is_painted_out_but_a_border_picture_is_not():
    img, page = sheet(edge=True)
    flat, _ = pagelayout.level_page(img, page)
    assert np.asarray(flat.convert('L'))[:, :14].min() > 200
    # a colored border: not plain paper inside it, so it stays
    border = Image.new('RGB', (600, 800), (40, 120, 40))
    ImageDraw.Draw(border).rectangle((40, 40, 560, 760), fill=(245, 235, 210))
    assert pagelayout._edge_strips(np.asarray(border.convert('L'))) is None


# ---------------------------------------------------------------- QuizScan's boxes onto the lines

def test_creeping_boxes_are_laid_back_on_their_lines():
    img, page = sheet()
    H = img.size[1]
    crept = json.loads(json.dumps(page))
    for i, p in enumerate(crept['problems']):
        # a bit further down the page each row, a whole row off by the bottom
        shift = (i // 2) * 0.012
        p['box'] = dict(p['box'], top=p['box']['top'] + shift, bottom=p['box']['bottom'] + shift)
    snapped = pagelayout.snap_boxes(img, crept)
    for want, got in zip(page['problems'], snapped['problems']):
        mid = lambda b: (b['top'] + b['bottom']) / 2 * H
        assert abs(mid(want['box']) - mid(got['box'])) < 15, got['id']
    assert len(pagelayout.find_slots(img, crept)) == len(page['problems'])


def test_the_printed_label_is_never_covered():
    img, page = sheet()
    slots = pagelayout.find_slots(img, page, covered={p['id'] for p in page['problems']})
    for p in page['problems']:
        s = slots[p['id']]
        assert s['text']['left'] > p['box']['left'] + 0.04, p['id']   # after the label
        assert s['text']['right'] <= s['answer']['left'] + 0.01       # before the blank


# ---------------------------------------------------------------- the AI's check

@pytest.fixture
def page_job(app_db):
    app, db = app_db
    from app.qgen.models import ScanJob
    from app.user.models import User
    login(app, 'teach')
    teach = User.query.filter_by(username='teach').one()
    job = ScanJob(author_id=teach.id, name='Book', pages=1, data='{"pages": []}')
    db.session.add(job)
    db.session.commit()
    return job, teach


def run_check(job, teach, checks, slots=None, img_page=None):
    img, page = img_page or sheet(rows=3)
    slots = pagelayout.find_slots(img, page) if slots is None else slots
    fake = FakeStreamClient([], checks=checks)
    out, report = scan.check_places(job, 1, img, page, slots, set(), 'key', teach.id, client=fake)
    return out, report, fake, page


def test_the_check_stops_when_all_is_well(page_job):
    job, teach = page_job
    from app.qgen.models import AICall
    out, report, fake, _ = run_check(job, teach, [{'all_good': True, 'fixes': []}])
    assert report == {'rounds': 1, 'moved': 0, 'error': None} and len(fake.check_calls) == 1
    # it sees the page with its places drawn on, and the list of problems
    content = fake.check_calls[0]['messages'][0]['content']
    assert content[0]['type'] == 'image' and '"1 a."' in content[1]['text']
    assert AICall.query.filter(AICall.request.like('%: check 1')).count() == 1


def test_a_missing_place_is_added_on_its_own_line_only(page_job):
    job, teach = page_job
    img, page = sheet(rows=3)
    slots = pagelayout.find_slots(img, page)
    p2 = page['problems'][1]
    del slots[p2['id']]
    line = p2['box']
    right = {k: round(v, 4) for k, v in box(line['right'] - 0.1, line['top'] + 0.005, line['right'] - 0.01, line['bottom'] - 0.005).items()}
    checks = [{'all_good': False, 'fixes': [
        {'id': p2['id'], 'answer': right, 'text': None, 'why': 'missing'},
        # never a new problem
        {'id': 'q99', 'answer': right, 'text': None, 'why': 'made up'},
    ]}, {'all_good': True, 'fixes': []}]
    out, report, fake, _ = run_check(job, teach, checks, slots, (img, page))
    assert out[p2['id']]['answer'] == right and 'q99' not in out
    assert report['rounds'] == 2 and report['moved'] == 1


def test_moves_that_break_the_rules_are_refused(page_job):
    job, teach = page_job
    img, page = sheet(rows=3)
    slots = pagelayout.find_slots(img, page)
    p1, p3 = page['problems'][0], page['problems'][2]
    before = json.loads(json.dumps(slots))
    checks = [{'all_good': False, 'fixes': [
        # onto another problem's line (two rows down)
        {'id': p1['id'], 'answer': p3['box'] | {'left': 0.38, 'right': 0.49}, 'text': None, 'why': 'x'},
        # over another problem's place
        {'id': p3['id'], 'answer': slots[p1['id']]['answer'], 'text': None, 'why': 'x'},
        # not a real box
        {'id': p1['id'], 'answer': box(0.5, 0.5, 0.4, 0.6), 'text': None, 'why': 'x'},
    ]}]
    out, report, fake, _ = run_check(job, teach, checks, slots, (img, page))
    assert out == before
    # nothing taken: no second look
    assert report['moved'] == 0 and len(fake.check_calls) == 1


def test_at_most_three_looks_and_errors_keep_the_places(page_job):
    job, teach = page_job
    img, page = sheet(rows=3)
    slots = pagelayout.find_slots(img, page)
    p1 = page['problems'][0]
    a = slots[p1['id']]['answer']
    nudge = lambda d: {'all_good': False, 'fixes': [{'id': p1['id'], 'answer': dict(a, left=a['left'] + d, right=a['right'] + d), 'text': None, 'why': 'nudge'}]}
    out, report, fake, _ = run_check(job, teach, [nudge(0.002), nudge(0.004), nudge(0.006), nudge(0.008)], slots, (img, page))
    assert len(fake.check_calls) == scan.CHECK_ROUNDS == 3 and report['rounds'] == 3
    # an AI error: the places found so far are kept, and the error noted
    import anthropic
    fake = FakeStreamClient([], error=anthropic.APIConnectionError(request=None))
    out, report = scan.check_places(job, 1, img, page, slots, set(), 'key', teach.id, client=fake)
    assert out == slots and report['error'] and report['rounds'] == 0


def test_the_check_counts_against_the_hourly_limit(page_job):
    job, teach = page_job
    from datetime import datetime
    from app import db, tuning
    from app.qgen.models import AICall
    for _ in range(tuning.get('ai_hourly')):
        db.session.add(AICall(user_id=teach.id, created=datetime.now(), kind='problem', request='x', ok=True))
    db.session.commit()
    out, report, fake, _ = run_check(job, teach, [])
    assert report['rounds'] == 0 and not fake.check_calls


# ---------------------------------------------------------------- the page's own labels

def test_labels_from_the_page():
    from app.qgen.routes import _label
    assert _label('1 a.') == '1 a.' and _label('3)') == '3' and _label('(4)') == '4' and _label(None) == ''


def test_a_page_quiz_shows_the_pages_labels(app_db):
    app, db = app_db
    from app.qgen.models import VQuiz
    from app.qgen import routes
    vq = SimpleNamespace(id=-1, shuffle_order=False, vpid_lst='[1, 2]',
                         page_layout={'ids': [1, 2], 'labels': {'1': '1 a.', '2': '1 b.'}, 'pages': [], 'slots': []})
    with app.test_request_context():
        assert routes.qlabel(vq, 1) == '1 a.' and routes.qlabel(vq, 2) == '1 b.'
    # shuffled: the page no longer matches, so the quiz's own numbers
    vq2 = SimpleNamespace(**dict(vq.__dict__, id=-2, shuffle_order=True))
    with app.test_request_context():
        assert routes.qlabel(vq2, 1) == 1
    # a page labeling only some: none of them
    vq3 = SimpleNamespace(**dict(vq.__dict__, id=-3, page_layout=dict(vq.page_layout, labels={'1': '1 a.', '2': ''})))
    with app.test_request_context():
        assert routes.qlabel(vq3, 1) == 1
