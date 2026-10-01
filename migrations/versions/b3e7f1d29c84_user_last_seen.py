"""When each user was last active (for the Dashboard's "Right now")

Revision ID: b3e7f1d29c84
Revises: a8d4e2c7f915
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3e7f1d29c84'
down_revision = 'a8d4e2c7f915'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch:
        batch.add_column(sa.Column('last_seen', sa.DateTime(), nullable=True))
        batch.create_index('ix_user_last_seen', ['last_seen'])


def downgrade():
    with op.batch_alter_table('user') as batch:
        batch.drop_index('ix_user_last_seen')
        batch.drop_column('last_seen')
