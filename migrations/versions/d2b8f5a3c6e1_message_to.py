"""A student's message can go to chosen teachers instead of all of them

Revision ID: d2b8f5a3c6e1
Revises: c7a1e4b9d2f3
Create Date: 2026-10-02

"""
from alembic import op
import sqlalchemy as sa


revision = 'd2b8f5a3c6e1'
down_revision = 'c7a1e4b9d2f3'
branch_labels = None
depends_on = None


def upgrade():
    #every message so far went to all teachers
    with op.batch_alter_table('message') as batch:
        batch.add_column(sa.Column('to_all', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table('message_to',
                    sa.Column('message_id', sa.Integer(), sa.ForeignKey('message.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True))
    op.create_index('ix_message_to_user_id', 'message_to', ['user_id'])


def downgrade():
    #(dropping the table drops its index; MySQL won't drop it first, as the foreign key uses it)
    #note: messages written to one teacher become visible to all teachers again
    op.drop_table('message_to')
    with op.batch_alter_table('message') as batch:
        batch.drop_column('to_all')
