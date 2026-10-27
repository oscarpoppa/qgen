"""Teachers' notes about a person, on People: user.teacher_note, teacher_note_at, teacher_note_by_id (the owner, 2026-10-27)

Revision ID: e2b7c4d9a1f3
Revises: d9a3f6c1e8b4
Create Date: 2026-10-27

"""
from alembic import op
import sqlalchemy as sa


revision = 'e2b7c4d9a1f3'
down_revision = 'd9a3f6c1e8b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('teacher_note', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('teacher_note_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('teacher_note_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_user_teacher_note_by', 'user', ['teacher_note_by_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_constraint('fk_user_teacher_note_by', type_='foreignkey')
        batch_op.drop_column('teacher_note_by_id')
        batch_op.drop_column('teacher_note_at')
        batch_op.drop_column('teacher_note')
