"""A student can remove a teacher's message from their own view

Revision ID: c7d1a5e38b24
Revises: b4c8e2f19a63
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7d1a5e38b24'
down_revision = 'b4c8e2f19a63'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('message', schema=None) as batch_op:
        #the student removed this teacher's message from their own view (teachers still see it)
        batch_op.add_column(sa.Column('hidden_for_student', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.drop_column('hidden_for_student')
