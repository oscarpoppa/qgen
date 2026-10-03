"""Teachers can write to other teachers

Revision ID: e4c9a7b1d3f5
Revises: d2b8f5a3c6e1
Create Date: 2026-10-03

"""
from alembic import op
import sqlalchemy as sa


revision = 'e4c9a7b1d3f5'
down_revision = 'd2b8f5a3c6e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('staff_message',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('sender_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
                    sa.Column('body', sa.Text(), nullable=False),
                    sa.Column('created', sa.DateTime(), nullable=False),
                    sa.Column('to_all', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index('ix_staff_message_sender_id', 'staff_message', ['sender_id'])
    op.create_index('ix_staff_message_created', 'staff_message', ['created'])
    op.create_table('staff_message_to',
                    sa.Column('message_id', sa.Integer(), sa.ForeignKey('staff_message.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True))
    op.create_index('ix_staff_message_to_user_id', 'staff_message_to', ['user_id'])
    op.create_table('staff_message_read',
                    sa.Column('message_id', sa.Integer(), sa.ForeignKey('staff_message.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True))
    op.create_index('ix_staff_message_read_user_id', 'staff_message_read', ['user_id'])


def downgrade():
    #(dropping a table drops its indexes; MySQL won't drop one a foreign key uses first)
    op.drop_table('staff_message_read')
    op.drop_table('staff_message_to')
    op.drop_table('staff_message')
