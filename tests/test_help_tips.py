"""The "?" help tips on the problem editor."""
import re

from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)


def tips(page):
    return re.findall(r'<button type="button" class="tip" aria-label="Help: ([^"]+)"[^>]*>\?</button>'
                      r'<span class="tip-body" role="tooltip" hidden>(.*?)</span></span>', page, re.S)


def test_problem_editor_has_help_everywhere(app_db):
    app, db = app_db
    page = login(app, 'teach').get('/quiz/makevprob').data.decode()
    found = tips(page)
    labels = {label for label, _ in found}
    for want in ('Question type', 'Title', 'Question', 'random values', 'value names', 'kinds of value',
                 'value settings', 'How close must the answer be?', 'pictures', 'Calculator allowed'):
        assert want in labels, want
    # every tip says something, and its markup arrived as markup (not escaped text)
    assert all(body.strip() for _, body in found)
    assert '&lt;p&gt;' not in page and '<p>A formula using your value names' in page
    # numbered steps, the live kind line, and the value-name chip bars
    assert page.count('class="step-num"') == 5
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
