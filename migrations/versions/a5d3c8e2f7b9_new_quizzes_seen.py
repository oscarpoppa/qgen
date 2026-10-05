"""A quiz given to someone counts next to "My quizzes" until they open that page

Revision ID: a5d3c8e2f7b9
Revises: e4c9a7b1d3f5
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa


revision = 'a5d3c8e2f7b9'
down_revision = 'e4c9a7b1d3f5'
branch_labels = None
depends_on = None


def upgrade():
    #quizzes already given aren't new: nothing is counted until the next one
    with op.batch_alter_table('cquiz') as batch:
        batch.add_column(sa.Column('seen_by_taker', sa.Boolean(), nullable=False, server_default=sa.true()))
    #teachers' Notices panels now show notices about quizzes they take; the ones from
    #before this change start out read, so they don't all show up as new at once
    message = sa.table('message', sa.column('kind', sa.String), sa.column('from_teacher', sa.Boolean),
                       sa.column('student_id', sa.Integer), sa.column('seen_by_student', sa.Boolean))
    user = sa.table('user', sa.column('id', sa.Integer), sa.column('is_admin', sa.Boolean))
    op.execute(message.update()
               .where(message.c.kind == 'notice', message.c.from_teacher.is_(True), message.c.seen_by_student.is_(False),
                      message.c.student_id.in_(sa.select(user.c.id).where(user.c.is_admin.is_(True))))
               .values(seen_by_student=True))


def downgrade():
    with op.batch_alter_table('cquiz') as batch:
        batch.drop_column('seen_by_taker')
