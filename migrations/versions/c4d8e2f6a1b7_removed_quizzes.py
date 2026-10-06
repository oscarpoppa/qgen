"""Removed quizzes: a quiz taken off the Quizzes page (and Assign) while students keep their
copies and scores; it can be brought back

Revision ID: c4d8e2f6a1b7
Revises: b3e7d1a5c9f2
Create Date: 2026-10-06

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4d8e2f6a1b7'
down_revision = 'b3e7d1a5c9f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vquiz') as batch:
        batch.add_column(sa.Column('removed_at', sa.DateTime(), nullable=True))


def downgrade():
    #SQLite drops a plain column in place (rebuilding the table would trip the foreign keys
    #of the attempts that point at it)
    if op.get_bind().dialect.name == 'sqlite':
        op.execute('ALTER TABLE vquiz DROP COLUMN removed_at')
        return
    with op.batch_alter_table('vquiz') as batch:
        batch.drop_column('removed_at')
