"""Delete grayed (and refused) while something still uses it (the owner, 2026-10-26, To do 65): a picture or file a
problem or quiz uses; a quiz someone is taking right now."""
import os
from datetime import datetime

from test_flow import app_db, login  # noqa: F401  (fixture)
from test_dashboard import make_quiz, give


def put_picture(name):
    from PIL import Image
    d = os.environ['STATIC_DIR'].rstrip('/') + '/'
    Image.new('RGB', (8, 8)).save(d + name)
    Image.new('RGB', (4, 4)).save(d + 'T_' + name)
    return d


def test_a_picture_in_use_cant_be_deleted(app_db):
    app, db = app_db
    from app.qgen import services as S
    teach = login(app, 'teach')
    d = put_picture('cat.png')
    put_picture('dog.png')
    vq = make_quiz(app, teach, 'Week 2')
    vq.image = 'cat.png'
    vp = vq.vproblems[0]
    vp.options = dict(vp.options, images=[{'file': 'cat.png', 'label': ''}])
    db.session.commit()
    with app.test_request_context():
        why = S.file_delete_blocker('cat.png', 'pictures')
        assert why == 'Picture “cat.png” is used by these problems: “{}”; and these quizzes: “Week 2”. Take it out of them first.'.format(vp.title)
        assert S.file_delete_blocker('dog.png', 'pictures') is None
    page = teach.get('/images').data.decode()
    assert why.replace('“', '&#8220;') in page or why in page  # the grayed Delete's tooltip
    # the server refuses too; an unused one goes
    teach.post('/delimg/cat.png')
    assert os.path.exists(d + 'cat.png')
    teach.post('/delimg/dog.png')
    assert not os.path.exists(d + 'dog.png')


def test_a_quiz_being_taken_has_its_trash_grayed(app_db):
    app, db = app_db
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, 'Week 3')
    cq = give(vq, 'sam')
    page = teach.get('/quiz/listvq').data.decode()
    assert 'taking “Week 3” right now' not in page
    cq.startdate = datetime.now()
    db.session.commit()
    page = teach.get('/quiz/listvq').data.decode()
    assert 'is taking “Week 3” right now. Try again once it’s handed in (or its time runs out).' in page


def test_a_problem_a_quiz_uses_has_its_trash_grayed_and_names_the_quiz(app_db):
    """A problem a quiz uses: its trash can grayed, naming the quizzes; the server refuses both Move to Trash and
    Delete; its opened row links to each quiz on Quizzes (the owner, 2026-10-26)."""
    app, db = app_db
    from app.qgen.models import VProblem
    teach = login(app, 'teach')
    vq = make_quiz(app, teach, 'Week 4')
    vp = vq.vproblems[0]
    page = teach.get('/quiz/listvp').data.decode()
    why = 'Problem “{}” is used by these quizzes: “Week 4”. Take it out of them first.'.format(vp.title)
    assert why in page
    assert 'In quizzes: <a class="name-link" href="/quiz/listvq/{}"'.format(vq.id) in page
    teach.post('/quiz/archivevp/{}'.format(vp.id))
    teach.post('/quiz/delvp/{}'.format(vp.id))
    db.session.expire_all()
    vp = db.session.get(VProblem, vp.id)
    assert vp is not None and vp.removed_at is None
