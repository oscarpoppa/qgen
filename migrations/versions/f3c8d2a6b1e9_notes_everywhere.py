"""Teachers' notes on problems, quizzes, pictures and files, and scanned workbooks (as People's), and a note to the
student on an assigned quiz, shared by its Assign group (the owner, 2026-10-28)

Revision ID: f3c8d2a6b1e9
Revises: e2b7c4d9a1f3
Create Date: 2026-10-28

"""
from alembic import op
import sqlalchemy as sa


revision = 'f3c8d2a6b1e9'
down_revision = 'e2b7c4d9a1f3'
branch_labels = None
depends_on = None

TABLES = ('vproblem', 'vquiz', 'upload_file', 'scan_job')


def sqlite():
    return op.get_bind().dialect.name == 'sqlite'


def upgrade():
    #(on SQLite the columns are just added: a foreign key there means rebuilding the table, which the tables pointing at
    #it refuse; the app sets the note's author itself, and MySQL gets the real foreign key)
    for t in TABLES:
        op.add_column(t, sa.Column('teacher_note', sa.Text(), nullable=True))
        op.add_column(t, sa.Column('teacher_note_at', sa.DateTime(), nullable=True))
        op.add_column(t, sa.Column('teacher_note_by_id', sa.Integer(), nullable=True))
        if not sqlite():
            op.create_foreign_key('fk_{}_teacher_note_by'.format(t), t, 'user', ['teacher_note_by_id'], ['id'], ondelete='SET NULL')
    op.add_column('cquiz', sa.Column('assign_note', sa.Text(), nullable=True))
    op.add_column('cquiz', sa.Column('assign_note_at', sa.DateTime(), nullable=True))
    op.add_column('cquiz', sa.Column('assign_group', sa.String(32), nullable=True))
    op.create_index('ix_cquiz_assign_group', 'cquiz', ['assign_group'])


def downgrade():
    op.drop_index('ix_cquiz_assign_group', 'cquiz')
    for c in ('assign_group', 'assign_note_at', 'assign_note'):
        op.drop_column('cquiz', c)
    for t in reversed(TABLES):
        if not sqlite():
            op.drop_constraint('fk_{}_teacher_note_by'.format(t), t, type_='foreignkey')
        for c in ('teacher_note_by_id', 'teacher_note_at', 'teacher_note'):
            op.drop_column(t, c)
