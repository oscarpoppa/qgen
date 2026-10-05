"""A teacher's "X assigned ... to 1 student" notice shows the student's picture: file the
existing ones under the student (they were under the assigning teacher)

Revision ID: f3c8d6b2a4e1
Revises: e7b5c2a9d1f4
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa


revision = 'f3c8d6b2a4e1'
down_revision = 'e7b5c2a9d1f4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    message = sa.table('message', sa.column('id', sa.Integer), sa.column('kind', sa.String), sa.column('from_teacher', sa.Boolean),
                       sa.column('body', sa.Text), sa.column('link', sa.String), sa.column('student_id', sa.Integer))
    cquiz = sa.table('cquiz', sa.column('id', sa.Integer), sa.column('assignee', sa.Integer))
    user = sa.table('user', sa.column('id', sa.Integer))
    rows = conn.execute(sa.select(message.c.id, message.c.link)
                        .where(message.c.kind == 'notice', message.c.from_teacher.is_(False),
                               message.c.body.like('% assigned "%" to 1 student: %'))).fetchall()
    for mid, link in rows:
        tail = (link or '').rsplit('/', 1)[-1]
        if not tail.isdigit():
            continue
        if link.startswith('/quiz/take/'):
            row = conn.execute(sa.select(cquiz.c.assignee).where(cquiz.c.id == int(tail))).first()
            who = row.assignee if row else None
        elif link.startswith('/quiz/listuser/'):
            who = int(tail) if conn.execute(sa.select(user.c.id).where(user.c.id == int(tail))).first() else None
        else:
            who = None
        if who:
            conn.execute(message.update().where(message.c.id == mid).values(student_id=who))


def downgrade():
    pass  # only whose picture shows; nothing to undo
