"""Folders on the Users page (shared by the teachers)

Revision ID: c3f9a1d7e5b2
Revises: b8e1f4c6a2d7
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3f9a1d7e5b2'
down_revision = 'b8e1f4c6a2d7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('user_folder',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('parent_id', sa.Integer(), sa.ForeignKey('user_folder.id', ondelete='CASCADE'), nullable=True),
                    sa.Column('name', sa.String(length=64), nullable=False),
                    sa.Column('created', sa.DateTime(), nullable=False))
    op.create_index(op.f('ix_user_folder_parent_id'), 'user_folder', ['parent_id'])
    op.create_table('user_folder_member',
                    sa.Column('folder_id', sa.Integer(), sa.ForeignKey('user_folder.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True))
    op.create_index(op.f('ix_user_folder_member_user_id'), 'user_folder_member', ['user_id'])


def downgrade():
    #their indexes go with them (MySQL won't drop an index a foreign key still needs)
    op.drop_table('user_folder_member')
    op.drop_table('user_folder')
