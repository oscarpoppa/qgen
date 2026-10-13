"""A teacher can clear teachers' messages from their own view ("Clear")

Revision ID: a4c7e2f9b1d3
Revises: e1a7c3b5d9f2
Create Date: 2026-10-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4c7e2f9b1d3'
down_revision = 'e1a7c3b5d9f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('staff_message_read', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cleared', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('staff_message_read', schema=None) as batch_op:
        batch_op.drop_column('cleared')
