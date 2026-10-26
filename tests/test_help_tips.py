"""The problem editor's labels: no help tooltips any more (the owner, 2026-10-26)."""
import re

from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)


def tips(page):
    return re.findall(r'<button type="button" class="tip" aria-label="Help: ([^"]+)"[^>]*>\?</button>'
                      r'<span class="tip-body" role="tooltip" hidden>(.*?)</span></span>', page, re.S)


def test_no_help_tooltips_on_labels(app_db):
    """No label tooltips with the dotted underline and "?" cursor (the owner, 2026-10-26)."""
    app, db = app_db
    teach = login(app, 'teach')
    for url in ('/quiz/makevprob', '/quiz/makevquiz', '/dashboard'):
        page = teach.get(url).data.decode()
        assert not tips(page) and 'class="tip-wrap"' not in page, url
    page = teach.get('/quiz/makevprob').data.decode()
    # numbered steps (Calculator and Folder each a card: the owner, 2026-10-26), the live kind line, the value-name chips
    assert page.count('class="step-num"') == 6
    assert 'class="kind-hint"' in page and page.count('class="name-chips"') == 2


def test_tips_never_sit_inside_a_paragraph(app_db):
    # a <p> inside a tip would end an enclosing <p> early and spill the tip onto the page
    app, db = app_db
    page = login(app, 'teach').get('/quiz/makevprob').data.decode()
    for para in re.findall(r'<p\b[^>]*>(.*?)</p>', page, re.S):
        assert 'class="tip-body"' not in para


def test_tip_form_still_saves(app_db):
    # the extra markup doesn't change what the form sends
    app, db = app_db
    teacher = login(app, 'teach')
    r = teacher.post('/quiz/makevprob', data=problem_form('numeric', 'Tips', 'What is [a] + 1?', 'a + 1',
                                                             values=[{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '9'}]))
    assert r.status_code == 302
