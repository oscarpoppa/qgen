"""Made by the scanner (the owner, 2026-10-25): a mark on quizzes, problems and their folders the scanner made, so
they show a small camera beside their names. Those already made are marked here: a quiz with a page layout (only
the scanner makes those); a problem in such a quiz, made within ten minutes of it (not one the scan reused); a folder
whose things (or, with none of its own, whose folders) are all made by the scanner.

Revision ID: a7d3e9f1c2b4
Revises: e5b9c3a1d7f2
Create Date: 2026-10-25
"""
from datetime import timedelta

from alembic import op
import sqlalchemy as sa

revision = 'a7d3e9f1c2b4'
down_revision = 'e5b9c3a1d7f2'
branch_labels = None
depends_on = None

TABLES = ('vquiz', 'vproblem', 'vqgroup', 'vpgroup')


def upgrade():
    #(a plain ADD COLUMN, not a batch: on SQLite a batch copies the whole table and drops the old one, which its
    #foreign keys refused, 2026-10-25)
    for t in TABLES:
        op.add_column(t, sa.Column('from_scan', sa.Boolean(), nullable=False, server_default=sa.false()))
    bind = op.get_bind()
    quizzes = {qid: made for qid, made in bind.execute(sa.text('SELECT id, create_date FROM vquiz WHERE page_layout IS NOT NULL'))}
    problems = set()
    for pid, made, qid in bind.execute(sa.text('SELECT p.id, p.create_date, pq.vquiz_id FROM vproblem p '
                                               'JOIN vproblem_vquiz pq ON pq.vproblem_id = p.id')):
        when = quizzes.get(qid)
        if when is not None and made is not None and abs(_dt(made) - _dt(when)) <= timedelta(minutes=10):
            problems.add(pid)
    _mark(bind, 'vquiz', quizzes)
    _mark(bind, 'vproblem', problems)
    _folders(bind, 'vqgroup', 'vquiz_vqgroup', 'vquiz_id', 'vqgroup_id', set(quizzes))
    _folders(bind, 'vpgroup', 'vproblem_vpgroup', 'vproblem_id', 'vpgroup_id', problems)


def _dt(v):
    if isinstance(v, str):
        from datetime import datetime
        return datetime.fromisoformat(v)
    return v


def _mark(bind, table, ids):
    for i in ids:
        bind.execute(sa.text('UPDATE {} SET from_scan = :t WHERE id = :i'.format(table)), {'t': True, 'i': i})


def _folders(bind, table, link, item_col, group_col, scanned):
    groups = {gid: parent for gid, parent in bind.execute(sa.text('SELECT id, parent_id FROM {}'.format(table)))}
    items = {}
    for iid, gid in bind.execute(sa.text('SELECT {}, {} FROM {}'.format(item_col, group_col, link))):
        items.setdefault(gid, set()).add(iid)
    marked = {g for g, its in items.items() if g in groups and its and its <= scanned}
    #(a folder with nothing of its own, whose folders are all marked: the workbook's top Problems folder)
    while True:
        more = {g for g in groups if g not in marked and not items.get(g)
                and [c for c, p in groups.items() if p == g] and all(c in marked for c, p in groups.items() if p == g)}
        if not more:
            break
        marked |= more
    _mark(bind, table, marked)


def downgrade():
    for t in TABLES:
        op.drop_column(t, 'from_scan')
