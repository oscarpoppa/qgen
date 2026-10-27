"""Move to Trash for the checked ones, and a Trash for Pictures and Other files (the owner, 2026-10-26, To do 66)."""
import os

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_dashboard import make_quiz
from test_delete_in_use import put_picture


def trash():
    return os.environ['UPLOAD_TRASH_DIR'].rstrip('/') + '/'


def row(db, name):
    from app.qgen.models import UploadFile
    db.session.expire_all()
    return UploadFile.query.filter_by(name=name).first()


def test_a_picture_goes_to_the_trash_and_comes_back(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    d = put_picture('owl.png')
    teach.get('/images')  # (its row)
    u = row(db, 'owl.png')
    teach.post('/upload/{}/trash'.format(u.id))
    assert not os.path.exists(d + 'owl.png') and os.path.exists(trash() + 'owl.png') and os.path.exists(trash() + 'T_owl.png')
    page = teach.get('/images').data.decode()
    assert 'data-name="owl.png"' not in page  # (its row kept by the sync, off the page)
    assert row(db, 'owl.png').removed_at is not None
    tpage = teach.get('/quiz/archive?section=pictures').data.decode()
    assert 'owl.png' in tpage and 'Pictures (1)' in tpage
    assert teach.get('/upload/trashed/owl.png').status_code == 200
    # a new upload of the same name never takes the trashed one's name
    from app.upload.routes import unique_name
    with app.test_request_context():
        assert unique_name('owl.png') == 'owl-2.png'
    teach.post('/upload/{}/restore'.format(u.id))
    assert os.path.exists(d + 'owl.png') and os.path.exists(d + 'T_owl.png') and not os.path.exists(trash() + 'owl.png')
    assert row(db, 'owl.png').removed_at is None


def test_delete_for_good_from_the_trash(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    put_picture('bat.png')
    teach.get('/images')
    u = row(db, 'bat.png')
    teach.post('/upload/{}/trash'.format(u.id))
    teach.post('/upload/{}/delete'.format(u.id))
    assert row(db, 'bat.png') is None and not os.path.exists(trash() + 'bat.png')


def test_students_cant_see_a_trashed_picture(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    put_picture('fox.png')
    teach.get('/images')
    teach.post('/upload/{}/trash'.format(row(db, 'fox.png').id))
    sam = login(app, 'sam')
    assert sam.get('/upload/trashed/fox.png').status_code != 200


def test_the_logo_and_a_used_picture_stay(app_db):
    app, db = app_db
    from app.qgen.models import Setting
    teach = login(app, 'teach')
    d = put_picture('logo.png')
    put_picture('cat.png')
    vq = make_quiz(app, teach, 'Week 2')
    vq.image = 'cat.png'
    Setting.put('logo', 'logo.png')
    db.session.commit()
    teach.get('/images')
    ids = [row(db, 'logo.png').id, row(db, 'cat.png').id]
    r = teach.post('/quiz/trash/pictures', data={'items': ids}, follow_redirects=True)
    page = r.data.decode()
    assert 'Not moved.' in page and 'site’s logo' in page.replace('&#8217;', '’')
    assert os.path.exists(d + 'logo.png') and os.path.exists(d + 'cat.png')


def test_checked_problems_and_quizzes_go_to_the_trash(app_db):
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, 'Week 4')
    used = vq.vproblems[0]
    loose = VProblem(title='Loose one', qtype='numeric', raw_prob='1 + 1 = ?', raw_ansr='2')
    db.session.add(loose)
    db.session.commit()
    r = teach.post('/quiz/trash/problems', data={'items': [loose.id, used.id]}, follow_redirects=True)
    page = r.data.decode()
    assert 'Moved 1 problem to the' in page and 'Not moved.' in page
    db.session.expire_all()
    assert db.session.get(VProblem, loose.id).removed_at is not None
    assert db.session.get(VProblem, used.id).removed_at is None
    teach.post('/quiz/trash/quizzes', data={'items': [vq.id]})
    db.session.expire_all()
    assert db.session.get(VQuiz, vq.id).removed_at is not None
    assert db.session.get(VProblem, used.id).removed_at is None  # (its problems stay)
