#!/usr/bin/env python
"""Add demo students, problems and quizzes to a database, for trying the app.

    python scripts/seed_demo.py --env .env.quiztest

Safe to run more than once: anything that already exists (same username or
title) is left alone. New students get random passwords, written to
.demo-accounts.txt (git-ignored) instead of the screen.
"""
import argparse
import os
import random
import secrets
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

STUDENTS = ['ava', 'ben', 'chloe', 'diego', 'emma', 'farid']

AB = [{'name': 'a', 'kind': 'whole', 'min': '2', 'max': '12'},
      {'name': 'b', 'kind': 'whole', 'min': '2', 'max': '12', 'different_from': ['a']}]

PROBLEMS = [
    dict(title='Demo: multiply', qtype='numeric', question='What is [a] × [b]?', answer='a * b', values=AB),
    dict(title='Demo: train distance', qtype='numeric',
         question='[who] rides a train at [speed] mph for [hours] hours. How many miles does [who] travel?',
         answer='speed * hours',
         values=[{'name': 'who', 'kind': 'list', 'items': 'Maria, Ahmed, Li, Sam, Priya, Diego'},
                 {'name': 'speed', 'kind': 'whole', 'min': '40', 'max': '80', 'step': '5'},
                 {'name': 'hours', 'kind': 'whole', 'min': '2', 'max': '6'}]),
    dict(title='Demo: price per item', qtype='numeric',
         question='[n] notebooks cost $[total]. How much does one notebook cost, in dollars?',
         answer='total / n',
         values=[{'name': 'n', 'kind': 'whole', 'min': '2', 'max': '6'},
                 {'name': 'each', 'kind': 'decimal', 'min': '1', 'max': '4', 'places': '2'},
                 {'name': 'total', 'kind': 'calc', 'formula': 'round(n * each, 2)'}]),
    dict(title='Demo: add (pick one)', qtype='choice_one', question='[a] + [b] = ?', values=AB,
         choices='*[a + b]\n[a + b + 1]\n[a + b - 1]\n[a * b]\n[a + b + 2]\n[2 * a + b]', show_n=4),
    dict(title='Demo: even numbers', qtype='choice_many', question='Which of these numbers are even? Check all that are.',
         choices='*2\n*4\n*6\n*8\n*10\n3\n5\n7\n9\n11', show_n=5),
    dict(title='Demo: make ten', qtype='choice_many', question='Check two numbers that add up to 10.',
         values=[{'name': 'a', 'kind': 'whole', 'min': '1', 'max': '3'},
                 {'name': 'b', 'kind': 'whole', 'min': '6', 'max': '9'}],
         choices='[a]\n[10 - a]\n[b]\n[10 - b]\n[a + 11]', combos='[a], [10 - a]\n[b], [10 - b]'),
    dict(title='Demo: bigger number', qtype='truefalse', question='True or false: [a] is bigger than [b].',
         answer='a > b', values=AB),
    dict(title='Demo: capitals', qtype='text', question='What is the capital of [country]?', answer='[capital]',
         values=[{'name': 'country = capital', 'kind': 'list',
                  'items': 'France = Paris, Japan = Tokyo, Kenya = Nairobi, Peru = Lima, Canada = Ottawa, Egypt = Cairo'}]),
    dict(title='Demo: explain', qtype='essay',
         question='In two or three sentences, explain why multiplying [a] by [b] gives the same answer as multiplying [b] by [a].',
         values=AB, grading_notes='Look for: order of factors does not matter; an example or picture of groups.'),
]

QUIZZES = [
    dict(title='Demo: warm-up', problems=['Demo: multiply', 'Demo: add (pick one)', 'Demo: bigger number']),
    dict(title='Demo: mixed practice', problems=[
        'Demo: train distance',
        {'pick': 2, 'from': ['Demo: multiply', 'Demo: price per item', 'Demo: add (pick one)', 'Demo: make ten']},
        'Demo: even numbers', 'Demo: capitals', 'Demo: explain']),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--env', default='.env', help='settings file with DATABASE_URL (default .env)')
    ap.add_argument('--assign', action='store_true', help='also assign the demo quizzes to the demo students')
    args = ap.parse_args()

    from dotenv import dotenv_values
    settings = dotenv_values(os.path.join(HERE, args.env))
    os.environ['DATABASE_URL'] = settings['DATABASE_URL']
    os.environ.setdefault('SECRET_KEY', settings.get('SECRET_KEY') or 'seed-script')

    from app import app, db
    from app.user.models import User
    from app.qgen.models import VProblem, VQuiz, CQuiz, CProblem, VPGroup, VQGroup
    from app.qgen.qtypes import get_qtype
    from app.qgen import layout

    with app.app_context():
        print('Database:', db.engine.url.database)
        teacher = User.query.filter_by(is_admin=True).first()
        if not teacher:
            sys.exit('No administrator account found; create one first.')

        new_accounts = []
        for name in STUDENTS:
            if User.query.filter_by(username=name).first():
                continue
            pw = secrets.token_urlsafe(9)
            u = User(username=name)
            u.set_password(pw)
            db.session.add(u)
            new_accounts.append((name, pw))
        db.session.commit()

        archive_p = VPGroup.query.filter_by(title='Archive').first()
        by_title = {}
        for spec in PROBLEMS:
            vp = VProblem.query.filter_by(title=spec['title']).first()
            if not vp:
                options = {'markup': 'friendly', 'values': spec.get('values', []), 'choices': spec.get('choices', ''),
                           'combos': spec.get('combos', ''), 'shuffle': True, 'show_n': spec.get('show_n'),
                           'case_sensitive': False, 'grading_notes': spec.get('grading_notes', ''), 'images': []}
                errors = get_qtype(spec['qtype']).validate(spec['question'], spec.get('answer', ''), options)
                if errors:
                    sys.exit('Problem "{}" has errors: {}'.format(spec['title'], errors))
                vp = VProblem(title=spec['title'], qtype=spec['qtype'], raw_prob=spec['question'],
                              raw_ansr=spec.get('answer', ''), author_id=teacher.id, calculator_ok=False)
                vp.options = options
                if archive_p:
                    vp.vpgroups.append(archive_p)
                db.session.add(vp)
                db.session.commit()
                print('  added problem:', vp.title)
            by_title[spec['title']] = vp.id

        archive_q = VQGroup.query.filter_by(title='Archive').first()
        for spec in QUIZZES:
            vq = VQuiz.query.filter_by(title=spec['title']).first()
            if vq:
                continue
            lay = [{'pick': e['pick'], 'from': [by_title[t] for t in e['from']]} if isinstance(e, dict) else by_title[e]
                   for e in spec['problems']]
            vq = VQuiz(title=spec['title'], vpid_lst=layout.dumps(lay), author_id=teacher.id,
                       calculator_ok=False, shuffle_order=True)
            vq.vproblems = [db.session.get(VProblem, i) for i in set(layout.all_ids(lay))]
            if archive_q:
                vq.vqgroups.append(archive_q)
            db.session.add(vq)
            db.session.commit()
            print('  added quiz:', vq.title, '({} questions per student)'.format(layout.question_count(lay)))

        if args.assign:
            rng = random.Random()
            for spec in QUIZZES:
                vq = VQuiz.query.filter_by(title=spec['title']).first()
                for name in STUDENTS:
                    u = User.query.filter_by(username=name).first()
                    if not u or CQuiz.query.filter_by(vquiz_id=vq.id, assignee=u.id).first():
                        continue
                    cq = CQuiz(vquiz_id=vq.id, assignee=u.id)
                    ids = layout.draw(layout.parse(vq.vpid_lst), rng)
                    rng.shuffle(ids)
                    for o, pid in enumerate(ids, 1):
                        vp = db.session.get(VProblem, pid)
                        prob, ansr, opts = get_qtype(vp.qtype).instantiate(vp.raw_prob, vp.raw_ansr, vp.options, rng)
                        cp = CProblem(ordinal=o, conc_prob=prob, conc_ansr=ansr, vproblem_id=vp.id)
                        cp.conc_opts = opts
                        cq.cproblems.append(cp)
                    db.session.add(cq)
            db.session.commit()
            print('  assigned the demo quizzes to the demo students')

        if new_accounts:
            path = os.path.join(HERE, '.demo-accounts.txt')
            old = os.umask(0o077)
            with open(path, 'a') as f:
                f.write('# demo student accounts in {} (usernames and passwords)\n'.format(db.engine.url.database))
                for name, pw in new_accounts:
                    f.write('{}  {}\n'.format(name, pw))
            os.umask(old)
            print('  added {} students: {} (passwords in .demo-accounts.txt)'.format(
                len(new_accounts), ', '.join(n for n, _ in new_accounts)))


if __name__ == '__main__':
    main()
