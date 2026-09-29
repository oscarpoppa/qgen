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
