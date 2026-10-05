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
    #plain DROP COLUMN (MySQL, and SQLite 3.35+): a batch rebuild of these tables trips over
    #the foreign keys pointing at them on SQLite
    op.drop_column('vquiz', 'hide_answers')
    op.drop_column('vquiz', 'answers_released')
    op.drop_column('cquiz', 'answers_released')


def downgrade():
    #back as they started: nothing hidden
    op.add_column('vquiz', sa.Column('hide_answers', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('vquiz', sa.Column('answers_released', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('cquiz', sa.Column('answers_released', sa.Boolean(), nullable=False, server_default=sa.false()))
