"""a quiz made from a scanned page is taken on the page itself: vquiz.page_layout (2026-10-18)

Revision ID: a7d3f1c9e5b2
Revises: c4e9a1b7d2f6
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = 'a7d3f1c9e5b2'
down_revision = 'c4e9a1b7d2f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vquiz') as batch:
        batch.add_column(sa.Column('page_layout', sa.Text().with_variant(mysql.LONGTEXT(), 'mysql'), nullable=True))


def downgrade():
    with op.batch_alter_table('vquiz') as batch:
        batch.drop_column('page_layout')
