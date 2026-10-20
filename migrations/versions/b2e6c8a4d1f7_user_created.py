"""when each account was made: user.created_at (People's Created column, 2026-10-18)

Revision ID: b2e6c8a4d1f7
Revises: a7d3f1c9e5b2
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2e6c8a4d1f7'
down_revision = 'a7d3f1c9e5b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch:
        batch.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('user') as batch:
        batch.drop_column('created_at')
