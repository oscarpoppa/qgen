"""Correct answers always show on a finished quiz: the "hide answers until released" settings go

Revision ID: d4a2e8c1f6b3
Revises: c3f9a1d7e5b2
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4a2e8c1f6b3'
down_revision = 'c3f9a1d7e5b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vquiz') as batch:
        batch.drop_column('hide_answers')
        batch.drop_column('answers_released')
    with op.batch_alter_table('cquiz') as batch:
        batch.drop_column('answers_released')


def downgrade():
    #back as they started: nothing hidden
    with op.batch_alter_table('vquiz') as batch:
        batch.add_column(sa.Column('hide_answers', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column('answers_released', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('cquiz') as batch:
        batch.add_column(sa.Column('answers_released', sa.Boolean(), nullable=False, server_default=sa.false()))
