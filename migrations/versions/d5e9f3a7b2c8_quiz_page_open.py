"""Which quiz page someone has open right now (their page's check-ins), so the Dashboard's
"Taking a quiz" shows only quizzes being worked on at the moment

Revision ID: d5e9f3a7b2c8
Revises: c4d8e2f6a1b7
Create Date: 2026-10-06

"""
from alembic import op
import sqlalchemy as sa


revision = 'd5e9f3a7b2c8'
down_revision = 'c4d8e2f6a1b7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch:
        batch.add_column(sa.Column('on_quiz', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('on_quiz_at', sa.DateTime(), nullable=True))


def downgrade():
    #SQLite drops plain columns in place (rebuilding the table would trip foreign keys)
    if op.get_bind().dialect.name == 'sqlite':
        op.execute('ALTER TABLE user DROP COLUMN on_quiz_at')
        op.execute('ALTER TABLE user DROP COLUMN on_quiz')
        return
    with op.batch_alter_table('user') as batch:
        batch.drop_column('on_quiz_at')
        batch.drop_column('on_quiz')
