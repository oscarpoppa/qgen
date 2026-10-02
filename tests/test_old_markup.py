"""Removing everything tied to the old {{...}} markup (flask remove-old-markup)."""
import json

from test_flow import app_db, login, problem_form  # noqa: F401  (fixture)
from test_archive import ids


def test_remove_old_markup(app_db):
    app, db = app_db
    from app.qgen.models import VProblem, VQuiz, CQuiz, CProblem, ArchivedAttempt
    from app.messages.models import Message
    from app.qgen import services as S
    teacher = login(app, 'teach')

    teacher.post('/quiz/makevprob', data=problem_form('numeric', 'New one', 'What is 2 + 2?', '4', []))
    new = VProblem.query.filter_by(title='New one').one()
    assert new.options['markup'] == 'friendly'
    old = VProblem(title='Old one', qtype='numeric', raw_prob='{{a:ri(1,4)}} + 1 = ?', raw_ansr='{{a+1}}',
                   options_json=json.dumps({'markup': 'legacy'}))
    bare = VProblem(title='Old, unmarked', qtype='numeric', raw_prob='{{b:ri(1,4)}} = ?', raw_ansr='{{b}}')
    later = VProblem(title='Old, taken out later', qtype='numeric', raw_prob='{{c:ri(1,4)}} = ?', raw_ansr='{{c}}',
                     options_json=json.dumps({'markup': 'legacy'}))
    db.session.add_all([old, bare, later])
    db.session.commit()

    def quiz(title, *probs):
        vq = VQuiz(title=title, vpid_lst=json.dumps([p.id for p in probs]))
        vq.vproblems = list(probs)
        db.session.add(vq)
        db.session.commit()
        return vq

    def attempt(vq, *probs):
        cq = CQuiz(assignee=ids('sam'), vquiz_id=vq.id)
        db.session.add(cq)
        db.session.flush()
        for n, p in enumerate(probs):
            db.session.add(CProblem(cquiz_id=cq.id, vproblem_id=p.id, ordinal=n, conc_prob='x', conc_ansr='1'))
        db.session.add(Message(kind='notice', student_id=ids('sam'), body='assigned',
                               link='/quiz/take/{}'.format(cq.id)))
        db.session.commit()
        return cq

    keep_q = quiz('Only new', new)
    mixed_q = quiz('Mixed', new, old)
    bare_q = quiz('Unmarked', bare)
    later_q = quiz('Edited later', new, later)
    keep_cq = attempt(keep_q, new)
    mixed_cq = attempt(mixed_q, new, old)
    later_cq = attempt(later_q, new, later)
    # the quiz no longer uses that problem, but an attempt still has it
    later_q.vpid_lst = json.dumps([new.id])
    later_q.vproblems = [new]
    db.session.commit()
    ids_before = {'keep': keep_q.id, 'mixed': mixed_q.id, 'bare': bare_q.id, 'later': later_q.id,
                  'keep_cq': keep_cq.id, 'mixed_cq': mixed_cq.id, 'later_cq': later_cq.id}

    # a look first: nothing changes
    found = S.old_markup_cleanup()
    assert [t for _, t in found['problems']] == ['Old one', 'Old, unmarked', 'Old, taken out later']
    assert [t for _, t in found['quizzes']] == ['Mixed', 'Unmarked']
    assert [c for c, _, _ in found['attempts']] == [ids_before['mixed_cq'], ids_before['later_cq']]
    assert VProblem.query.count() == 4 and CQuiz.query.count() == 3

    # through the command: without --yes nothing goes
    out = app.test_cli_runner().invoke(args=['remove-old-markup']).output
    assert 'Old one' in out and 'Mixed' in out and 'Nothing deleted' in out
    assert VProblem.query.count() == 4

    out = app.test_cli_runner().invoke(args=['remove-old-markup', '--yes']).output
    assert 'Deleted.' in out
    db.session.expire_all()
    assert [p.title for p in VProblem.query.all()] == ['New one']
    assert sorted(q.title for q in VQuiz.query.all()) == ['Edited later', 'Only new']
    assert [c.id for c in CQuiz.query.all()] == [ids_before['keep_cq']]
    assert {c.vproblem_id for c in CProblem.query.all()} == {new.id}
    assert ArchivedAttempt.query.count() == 0  # deleted for good, not archived
    links = {m.link for m in Message.query.all()}
    assert links == {'/quiz/take/{}'.format(ids_before['keep_cq'])}

    # the rest still works, and running it again finds nothing
    assert teacher.get('/quiz/listvp').status_code == 200 and teacher.get('/quiz/listvq').status_code == 200
    assert S.old_markup_cleanup() == {'problems': [], 'quizzes': [], 'attempts': []}


def test_braces_are_plain_text_now(app_db):
    app, db = app_db
    from app.qgen.models import VProblem
    teacher = login(app, 'teach')
    teacher.post('/quiz/makevprob', data=problem_form('text', 'Set', 'Write the set {{1, 2}} in words.', 'one and two', []))
    vp = VProblem.query.filter_by(title='Set').one()
    assert vp.options['markup'] == 'friendly'
    assert 'old markup' not in teacher.get('/quiz/listvp').data.decode()
