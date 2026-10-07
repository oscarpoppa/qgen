import random

from app.qgen import layout


def test_old_and_new_formats():
    assert layout.parse('[4, 4, 5]') == [4, 4, 5]
    assert layout.parse('4, 7, 5') == [4, 7, 5]
    assert layout.parse('[1, {"pick": 2, "from": [5, 6, 7]}]') == [1, {'pick': 2, 'from': [5, 6, 7]}]
    assert layout.parse('') == []


def test_draw_picks_from_groups_and_keeps_singles():
    lay = [1, {'pick': 2, 'from': [5, 6, 7, 8]}, 9]
    seen = set()
    for seed in range(100):
        ids = layout.draw(lay, random.Random(seed))
        assert ids[0] == 1 and ids[-1] == 9 and len(ids) == 4
        assert len(set(ids[1:3])) == 2 and set(ids[1:3]) <= {5, 6, 7, 8}
        seen.add(tuple(ids[1:3]))
    assert len(seen) == 6  # every pair of 4 turns up
    assert layout.question_count(lay) == 4
    assert layout.all_ids(lay) == [1, 5, 6, 7, 8, 9]


def test_group_mistakes():
    assert 'at least two' in layout.check([{'pick': 1, 'from': [5]}])[0]
    assert 'not 3' in layout.check([{'pick': 3, 'from': [5, 6]}])[0]
    assert layout.check([{'pick': 2, 'from': [5, 6]}]) == []


def test_scripts_and_styles_are_versioned():
    # after an update, browsers must fetch the new files instead of a saved old copy
    import os, re
    from app import app
    app.config.update(TESTING=True)
    os.makedirs(os.path.join(app.static_folder, 'css'), exist_ok=True)
    path = os.path.join(app.static_folder, 'css', 'app.css')
    with open(path, 'w') as f:
        f.write('body {}')
    os.utime(path, (1790000000, 1790000000))
    page = app.test_client().get('/login').data.decode()
    links = re.findall(r'(?:href|src)="(/[^"]*\.(?:css|js)[^"]*)"', page)
    assert links and all(re.search(r'\?v=\d+$', l) for l in links), links
    assert any(l.endswith('css/app.css?v=1790000000') for l in links)


def test_my_quizzes_fold():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    page = open(os.path.join(root, 'app', 'user', 'templates', 'mypage.html')).read()
    assert '<details class="box card quiz-card"' in page and 'folders_page' in page and 'qgen-folded-quizzes' in page


def test_tests_always_use_a_throwaway_database():
    # the tests empty their database; it must be the in-memory one whatever the shell has
    from app import app
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite://'


def test_printing_a_quiz_leaves_out_the_rest_of_the_screen():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = open(os.path.join(root, 'static', 'css', 'app.css')).read()
    printing = css[css.index('@media print'):]
    for hidden in ('.topbar', '.dock', '.toast', '.no-print', 'ul.alerts'):
        assert hidden in printing.split('display: none')[0]
    assert '--text: #000000' in printing  # dark ink whatever the screen's theme
    for page in ('transcript.html', 'archived.html'):
        assert '<div class="page-head no-print">' in open(os.path.join(root, 'app', 'qgen', 'templates', page)).read()
