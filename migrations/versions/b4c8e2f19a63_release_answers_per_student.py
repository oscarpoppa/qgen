"""Release correct answers to one student at a time

Revision ID: b4c8e2f19a63
Revises: a9e3f05d7b18
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa


revision = 'b4c8e2f19a63'
down_revision = 'a9e3f05d7b18'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cquiz', schema=None) as batch_op:
        #correct answers shown to this student even though the quiz still hides them
        batch_op.add_column(sa.Column('answers_released', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('cquiz', schema=None) as batch_op:
        batch_op.drop_column('answers_released')
