"""Fixes from the code critic's review of 2026-10-20 (each found as a real failure)."""
import os

from test_flow import app_db, login  # noqa: F401  (fixture)

ROOT = os.path.join(os.path.dirname(__file__), '..')


def test_archive_restore_of_checked_items_sends(app_db):
    """The checked bar's Restore: its address is passed to the code that sends it (it was read
    from a name out of reach there, so nothing was ever sent)."""
    js = open(os.path.join(ROOT, 'static', 'js', 'filebar.js')).read()
    part = js[js.index('[data-restore-many]'):]
    assert 'send(b.dataset.url, ids)' in part and 'function send(url, ids)' in part and 'f.action = url' in part


def test_deleting_a_pictures_folder_with_a_picture_in_it(app_db):
    """Pictures and files have no removed date: deleting their folder works and says where they went."""
    app, db = app_db
    from app.qgen.models import UploadFile, PicGroup
    from app.qgen import services as S
    teacher = login(app, 'teach')
    pic = UploadFile(name='cat.png', picture=True)
    db.session.add(pic)
    db.session.commit()
    folder = S.create_subject('pictures', 'Animals')
    S.file_items('pictures', [pic.id], folder)
    db.session.commit()
    r = teacher.post('/quiz/subjects/pictures/{}/delete'.format(folder.id))
    assert r.status_code == 302
    assert PicGroup.query.count() == 0 and db.session.get(UploadFile, pic.id) is not None


def test_only_problems_and_quizzes_can_be_copied(app_db):
    app, db = app_db
    from app.qgen.models import UploadFile
    teacher = login(app, 'teach')
    pic = UploadFile(name='dog.png', picture=True)
    db.session.add(pic)
    db.session.commit()
    for kind in ('pictures', 'files', 'people', 'archive'):
        assert teacher.post('/quiz/copy/{}/{}'.format(kind, pic.id)).status_code == 404


def test_files_that_could_run_code_are_refused(app_db):
    """.html .htm .svg .js .xml are never uploaded (the owner, 2026-10-20)."""
    import io
    app, db = app_db
    teacher = login(app, 'teach')
    say = 'That kind of file can’t be uploaded: it could run code on the site.'
    for name in ('page.html', 'page.HTM', 'drawing.svg', 'code.js', 'feed.xml'):
        r = teacher.post('/upload/json?any=1', data={'file': (io.BytesIO(b'<script>alert(1)</script>'), name)},
                         headers={'X-CSRFToken': 'x'}, content_type='multipart/form-data')
        assert r.status_code == 400 and r.get_json()['error'] == say, name
        assert not os.path.exists(os.path.join(app.static_folder, name))
    # an ordinary other file still goes in
    r = teacher.post('/upload/json?any=1', data={'file': (io.BytesIO(b'hello'), 'allowed-check.txt')},
                     content_type='multipart/form-data')
    assert r.status_code == 200 and r.get_json()['ok']
    #(the test folder is shared: leave nothing behind)
    os.remove(os.path.join(app.config['STATIC_DIR'] if app.config.get('STATIC_DIR') else app.static_folder, r.get_json()['name']))


def test_move_dialog_counts_each_level_of_indent():
    """The Move dialog's folder list reads the indent folder_tree.indent writes: non-breaking
    spaces only, three per level (the critic thought plain spaces were mixed in; they aren't)."""
    from app.folder_tree import indent
    js = open(os.path.join(ROOT, 'static', 'js', 'filebar.js')).read()
    assert "text.match(/^\\u00a0+/)" in js
    assert indent(1) == '' and indent(3) == '\u00a0' * 6


def test_a_teacher_made_archive_folder_is_never_merged(app_db):
    """A folder the teacher made, named like a student, keeps its own attempts."""
    app, db = app_db
    from app.qgen import services as S
    from app.qgen.models import ArchiveFolder
    login(app, 'teach')
    mine = S.create_archive_folder('sam')
    assert mine.own_name
    S.ensure_archive_folders()
    assert db.session.get(ArchiveFolder, mine.id) is not None


def test_answer_boxes_never_get_inputmode_none():
    page = open(os.path.join(ROOT, 'app', 'qgen', 'templates', 'quiz_take.html')).read()
    assert "inputmode='numeric' if it.qtype == 'numeric' else none" not in page
    assert "{'inputmode': 'numeric'} if it.qtype == 'numeric' else {}" in page


def test_question_boxes_name_the_action():
    js = open(os.path.join(ROOT, 'static', 'js', 'confirm.js')).read()
    assert "okLabel || 'OK'" not in js and "form.dataset.confirmOk || own || 'Yes'" in js


def test_the_sites_own_address_goes_home_quietly(app_db):
    app, db = app_db
    teacher = login(app, 'teach')
    r = teacher.get('/', follow_redirects=True)
    assert 'already logged in' not in r.data.decode()
    r = teacher.get('/login', follow_redirects=True)
    assert 'already logged in' in r.data.decode()
