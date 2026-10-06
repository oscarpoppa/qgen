"""Nicknames: anyone can add one on My profile; it shows with their name all through the site

Revision ID: a9c4e2f7b1d3
Revises: f3c8d6b2a4e1
Create Date: 2026-10-06

"""
from alembic import op
import sqlalchemy as sa


revision = 'a9c4e2f7b1d3'
down_revision = 'f3c8d6b2a4e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('nickname', sa.String(length=32), nullable=True))


def downgrade():
    op.drop_column('user', 'nickname')
