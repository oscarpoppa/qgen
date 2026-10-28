"""The folder dialogs laid out like the Assign dialogs, and the reviewer's fixes alongside them (the
owner, 2026-10-22)."""
import json
import os
import re

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_archive import setup_quiz, ids

ROOT = os.path.join(os.path.dirname(__file__), '..')


def read(*path):
    return open(os.path.join(ROOT, *path)).read()


def archived(app, db, teacher):
    """sam's attempt archived, and a folder of the teacher's own with one inside it."""
    from app.qgen.models import CQuiz, ArchiveFolder, ArchivedAttempt
    vq, probs = setup_quiz(app, teacher, 'numeric')
    teacher.post('/quiz/assign', data={'vquiz': vq.id, 'users': [ids('sam')]})
    teacher.post('/quiz/delcq/{}'.format(CQuiz.query.one().id))
    teacher.post('/quiz/archive/folders/new', data={'name': 'Term 1'})
    term = ArchiveFolder.query.filter_by(name='Term 1').one()
    teacher.post('/quiz/archive/folders/new', data={'name': 'Week A', 'parent': term.id})
    week = ArchiveFolder.query.filter_by(name='Week A').one()
    return ArchivedAttempt.query.one(), term, week


def test_the_archives_rows_share_one_folder_list_not_a_hidden_drop_down_each(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    a, term, week = archived(app, db, teacher)
    page = teacher.get('/quiz/archive').data.decode()
    # no hidden "Move…" drop-down in each row (move_menu is gone too)
    assert 'move-select' not in page and 'Move…' not in page
    assert 'macro move_menu' not in read('app', 'templates', '_folders.html')
    # each row: its Move icon and the folder it's in now; the page: its folders once, with their icons
    row = page[page.index('data-box="attempt:{}"'.format(a.id)):]
    row = row[:row.index('</tr>')]
    assert 'data-move-one' in row and 'name="to" value=""' in row and 'name="from" value="{}"'.format(a.folder_id) in row
    folders = json.loads(re.search(r'<script type="application/json" id="move-folders">(.*?)</script>', page, re.S).group(1))
    assert folders['main'] == 'Uncategorized'
    by_name = {f[1]: f for f in folders['folders']}
    assert by_name['sam'][3] == 'user' and by_name['Term 1'][2] == 1 and by_name['Week A'][2] == 2
    # and the Move icon still moves it
    teacher.post('/quiz/archive/folders/move', data={'attempt': a.id, 'to': week.id, 'from': a.folder_id, 'view': 'all'})
    db.session.expire_all()
    assert a.folder_id == week.id


def test_a_folders_move_to_is_the_standard_picker(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    a, term, week = archived(app, db, teacher)
    page = teacher.get('/quiz/archive?folder={}'.format(week.id)).data.decode()
    box = page[page.index('data-fopt-dialog="move"'):]
    box = box[:box.index('</dialog>')]
    assert 'pick-dialog put-dialog' in page[page.index('data-fopt-dialog="move"') - 120:page.index('data-fopt-dialog="move"')]
    # the title, a short line, the amber box with only its lines
    assert 'Move “Week A” to another folder</strong><br>' in box and 'Choose the folder to move it to.' in box
    assert 'What happens:</strong>' in box and '<li>Everything in it moves with it</li>' in box
    # "Not inside another folder" pinned under All (the dialog's Uncategorized); itself left out;
    # the folder it's in now chosen to begin with
    holder = re.search(r'<div class="field pick-people folder-pick" data-folder-pick ([^>]*)>', box).group(1)
    assert 'data-main-label="Not inside another folder"' in holder and 'data-checked="{}"'.format(term.id) in holder
    rows = json.loads(re.search(r'<script type="application/json" data-pick-rows>(.*?)</script>', box, re.S).group(1))
    names = [r[1] for r in rows]
    assert 'Week A' not in names and 'Term 1' in names and 'sam' in names


def test_every_folder_dialog_is_built_the_same_way():
    """Put in folder, the checked bar's Move, a row's Move and a folder's Move to: the Assign dialogs'
    layout (pick-dialog, 820px), the standard picker from static/js/dialogfilter.js."""
    pick, bar, rows = read('static', 'js', 'dialogfilter.js'), read('static', 'js', 'filebar.js'), read('static', 'js', 'folders.js')
    # the rows indented one level per depth, 14px, the same as the side list's
    side = read('static', 'js', 'folderfilter.js')
    assert "if (depth > 1) r.style.paddingLeft = ((depth - 1) * 14) + 'px';" in side
    assert "if (f.depth > 1) lab.style.paddingLeft = ((f.depth - 1) * 14) + 'px';" in pick
    # "out of every folder" first, and Uncategorized in the side list only where it's offered
    assert "(o.top ? [{ id: 'top', name: o.top, depth: 1 }] : []).concat(folders)" in pick
    assert "if (holder.dataset.mainLabel) ds.mainLabel = holder.dataset.mainLabel; else ds.hideEmpty = '';" in pick
    assert "ds.allLabel = 'All Folders'" in pick and '<th>Folder</th>' in pick
    for js in (bar, rows):
        assert 'pick-dialog put-dialog' in js and 'qgenFolderPick.html()' in js and 'ul class="assign-many-people put-list"' not in js
    # Put in folder: "Copy instead" on its own line under the amber box, which keeps only its lines
    put = bar[bar.index("putBox.innerHTML"):]
    put = put[:put.index("document.body.appendChild(putBox)")]
    assert put.index('</ul></div>') < put.index('class="put-copy"') < put.index('qgenFolderPick.html()')
    # the Archive's Move: what it does is in the amber box, a short line under the title
    assert "'An attempt is in one folder at a time'" in bar and "Choose the folder to move ' + (n === 1 ? 'it' : 'them') + ' to.'" in bar
    assert 'in now. An attempt is in one folder' not in bar + rows
    # dialogfilter.js is ready before filebar.js builds its dialogs
    base = read('app', 'templates', 'base.html')
    assert base.index("js/dialogfilter.js") < base.index("js/filebar.js")


def test_the_put_dialog_has_no_uncategorized_and_the_checked_folder_comes_with_check_boxes():
    pick, side = read('static', 'js', 'dialogfilter.js'), read('static', 'js', 'folderfilter.js')
    assert 'box.qgenRedraw = function () { draw(); apply(); };' in side and 'window.qgenFolderFilterSetUp' in side
    # back on All when the check boxes go (no Checked folder without them)
    assert "if (!boxes().length && box.dataset.shown === 'checked') box.qgenChoose('all');" in pick


def test_no_tooltip_still_says_double_click_to_open_a_folder():
    for path in (('static', 'js', 'folderfilter.js'), ('static', 'js', 'pickpictures.js')):
        if os.path.exists(os.path.join(ROOT, *path)):
            assert "' (double-click: open this folder)'" not in read(*path)  # (the words as a string, not a comment)


def test_folder_options_closes_when_its_question_opens():
    js = read('static', 'js', 'confirm.js')
    ask = js[js.index("document.addEventListener('submit'"):]
    assert "var pop = form.closest('details.folder-tools[open]');" in ask and 'if (pop) pop.open = false;' in ask
    assert ask.index('pop.open = false') < ask.index('window.qgenAsk(form.dataset.confirm')


def test_people_fits_a_laptops_window(app_db):
    """Whole words in the name (the badge under it when there's no room), the date only, and the row
    icons a block in a narrow list (the reviewer, 2026-10-22: at 1300px the icons were off the edge)."""
    app, db = app_db
    from app.user.models import User
    teacher = login(app, 'teach')
    page = teacher.get('/userdet').data.decode()
    row = page[page.index('data-box="user:{}"'.format(ids('teach'))):]
    row = row[:row.index('</tr>')]
    #(a teacher's cap on the name's own line: the owner, 2026-10-24, To do 38)
    assert '<span class="person-line"><span class="avatar-wrap">' in row and '>teach</strong><span class="person-role person-role-icon"' in row
    made = User.query.filter_by(username='teach').one().created_at
    if made:
        from app import when_filter
        #(date and time, as before: the owner, 2026-10-22)
        assert '>{}</td>'.format(when_filter(made, 'date')) in row
    css = read('static', 'css', 'app.css')
    assert '.people-table .person .box-title { overflow-wrap: normal; word-break: normal; }' in css
    assert 'table.people-table td.person-folders { min-width: 0; max-width: 16rem; }' in css
    assert 'table.even-cols.people-table td.actions { white-space: normal;' in css


def _new_box(page, nth=0):
    at = [m.start() for m in re.finditer('data-fopt-dialog="new"', page)][nth]
    head = page[at - 120:at]
    box = page[at:]
    return head, box[:box.index('</dialog>')]


def test_new_folder_asks_where_it_goes(app_db):
    """New folder: the name and the standard picker, laid out like Move to; it starts on the folder looked
    at (or the top), and a folder already as deep as folders go is grayed with why (the owner, 2026-10-24)."""
    from test_tuning import set_values
    app, db = app_db
    teacher = login(app, 'teach')
    a, term, week = archived(app, db, teacher)
    head, box = _new_box(teacher.get('/quiz/archive').data.decode())
    assert 'pick-dialog put-dialog' in head
    assert '<strong>New folder</strong><br>' in box and 'Type its name and choose where it goes.' in box
    assert 'name="name"' in box and not re.search(r'<input[^>]* name="parent"', box)  # (the picker's round buttons are named parent)
    holder = re.search(r'<div class="field pick-people folder-pick" data-folder-pick ([^>]*)>', box).group(1)
    assert 'data-name="parent"' in holder and 'data-main-label="Not inside another folder"' in holder
    assert 'data-checked="top"' in holder
    assert box.index('Make Folder') < box.index('data-cancel')
    # inside Term 1: it starts there; one dialog on the page, and each folder's "+ New folder inside" opens it
    # on that folder (static/js/folders.js), not a copy of the folder list per folder
    page = teacher.get('/quiz/archive?folder={}'.format(term.id)).data.decode()
    assert page.count('data-fopt-dialog="new"') == 1
    assert 'data-checked="{}"'.format(term.id) in _new_box(page)[1]
    assert 'data-new-at="{}"'.format(term.id) in page
    js = read('static', 'js', 'folders.js')
    assert "b.dataset.newAt || holder.dataset.home" in js
    # two levels at most: Week A (level 2) is grayed with why, and can't be the start
    set_values(folder_depth=2)
    page = teacher.get('/quiz/archive?folder={}'.format(week.id)).data.decode()
    box = _new_box(page)[1]
    rows = {r[1]: r for r in json.loads(re.search(r'<script type="application/json" data-pick-rows>(.*?)</script>', box, re.S).group(1))}
    assert rows['Week A'][4] == 'Folders can go only 2 levels deep.' and rows['Term 1'][4] == ''
    assert 'data-checked="top"' in box
    # the chosen place is where it's made
    from app.qgen.models import ArchiveFolder
    teacher.post('/quiz/archive/folders/new', data={'name': 'Week B', 'parent': term.id})
    teacher.post('/quiz/archive/folders/new', data={'name': 'Loose', 'parent': 'top'})
    assert ArchiveFolder.query.filter_by(name='Week B').one().parent_id == term.id
    assert ArchiveFolder.query.filter_by(name='Loose').one().parent_id is None


def test_the_picker_grays_a_folder_that_cant_be_chosen():
    pick = read('static', 'js', 'dialogfilter.js')
    assert "off: f[4] || ''" in pick and 'i.disabled = true' in pick and "tr.title = f.off" in pick
    # a New folder dialog opens with the cursor in its name box, not the filter
    assert "d.querySelector('input[name=name]') || d.querySelector('input.filter-list')" in pick


def test_the_stashs_new_folder_is_the_same_dialog(app_db):
    app, db = app_db
    app.config['ANTHROPIC_API_KEY'] = 'test-key'  # (Scan workbook pages needs a key)
    teacher = login(app, 'teach')
    # (the stash's card shows once it has something: a folder made from it)
    from app.qgen.models import ScanFolder
    r = teacher.post('/quiz/scan/folders/new', data={'name': 'Book 1'})
    top = ScanFolder.query.filter_by(name='Book 1').one()
    assert top.parent_id is None and 'stash=' not in r.headers['Location']
    page = teacher.get('/quiz/scan').data.decode()
    at = page.index('id="stash-new"')
    assert 'pick-dialog put-dialog' in page[at - 120:at]
    box = page[at:page.index('</dialog>', at)]
    assert 'Type its name and choose where it goes.' in box and 'data-name="parent"' in box and 'data-checked="top"' in box
    assert 'data-checked="{}"'.format(top.id) in teacher.get('/quiz/scan?stash={}'.format(top.id)).data.decode()
    # made where chosen, and the stash stays where it was
    r = teacher.post('/quiz/scan/folders/new', data={'name': 'Ch 1', 'parent': top.id, 'view': 'main'})
    assert ScanFolder.query.filter_by(name='Ch 1').one().parent_id == top.id and 'stash=main' in r.headers['Location']
    app.config['ANTHROPIC_API_KEY'] = None
