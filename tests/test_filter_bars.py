"""Every filter box on the site is the standard one (the filter_bar macro, static/js/filter.js):
"Filter by name…", the same width, a count and Clear."""
import os
import re

from test_flow import app_db  # noqa: F401  (fixture)

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app')


def test_every_search_box_is_the_standard_bar():
    odd = []
    for folder, _dirs, files in os.walk(TEMPLATES):
        for f in files:
            if not f.endswith('.html'):
                continue
            path = os.path.join(folder, f)
            text = open(path, encoding='utf-8').read()
            for box in re.findall(r'<input[^>]*type="search"[^>]*>', text):
                if f == '_macros.html':
                    continue  # the bar itself
                if f == 'assign.html' and 'aria-label="Filter students"' in box:
                    continue  # Assign's Students: the model, with its own "chosen" count
                odd.append('{}: {}'.format(os.path.relpath(path, TEMPLATES), box[:80]))
            for word in ('placeholder="Search', 'placeholder="Find', 'placeholder="Filter…"', 'Filter users…'):
                assert word not in text, '{} still says {}'.format(path, word)
    assert not odd, 'search boxes outside the standard bar:\n' + '\n'.join(odd)


def test_the_pages_use_it(app_db):
    from test_flow import login, problem_form
    app, db = app_db
    teacher = login(app, 'teach')
    for i in range(7):
        teacher.post('/quiz/makevprob', data=problem_form('numeric', 'P{}'.format(i), '1 + [a] = ?', '1 + a',
                                                          [{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}]))
    page = teacher.get('/quiz/listvp?folder=all').data.decode()
    assert 'data-filter-bar' in page and 'data-many="problems"' in page and 'placeholder="Filter by name…"' in page
    # the quiz builder's problems too
    assert 'data-filter="#all-problems"' in teacher.get('/quiz/makevquiz').data.decode()
    # pictures: once there are more than five
    from test_flow import png_bytes
    for i in range(6):
        teacher.post('/upload/json', data={'file': (png_bytes('red'), 'p{}.png'.format(i))}, content_type='multipart/form-data')
    page = teacher.get('/images').data.decode()
    assert 'data-many="pictures"' in page and 'id="image-list"' in page and 'data-name="p0.png"' in page


def test_folder_list_has_expand_and_collapse_all(app_db):
    from test_flow import login
    app, db = app_db
    teacher = login(app, 'teach')
    from test_flow import problem_form
    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'One', '1 + 1 = ?', '2'))
    page = teacher.get('/quiz/listvp').data.decode()
    start = page.index('<nav aria-label="Folders">')
    side = page[start:page.index('</nav>', start)]
    assert 'data-side-level="open"' in side and 'data-side-level="close"' in side
    assert '<div class="btn-row small side-levels" hidden>' in side  # shown by its script when there's something to fold
