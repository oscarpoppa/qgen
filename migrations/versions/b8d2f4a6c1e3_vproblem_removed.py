"""A problem deleted while a quiz uses it (or students answered it) is kept but taken off the Problems page

Revision ID: b8d2f4a6c1e3
Revises: a4c7e2f9b1d3
Create Date: 2026-10-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8d2f4a6c1e3'
down_revision = 'a4c7e2f9b1d3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vproblem', schema=None) as batch_op:
        batch_op.add_column(sa.Column('removed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('vproblem', schema=None) as batch_op:
        batch_op.drop_column('removed_at')
