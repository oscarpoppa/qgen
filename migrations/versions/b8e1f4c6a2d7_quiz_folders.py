"""Folders on each person's own My quizzes page

Revision ID: b8e1f4c6a2d7
Revises: a5d3c8e2f7b9
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8e1f4c6a2d7'
down_revision = 'a5d3c8e2f7b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('quiz_folder',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('owner_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
                    sa.Column('parent_id', sa.Integer(), sa.ForeignKey('quiz_folder.id', ondelete='CASCADE'), nullable=True),
                    sa.Column('name', sa.String(length=64), nullable=False),
                    sa.Column('created', sa.DateTime(), nullable=False))
    op.create_index(op.f('ix_quiz_folder_owner_id'), 'quiz_folder', ['owner_id'])
    op.create_index(op.f('ix_quiz_folder_parent_id'), 'quiz_folder', ['parent_id'])
    op.create_table('quiz_placement',
                    sa.Column('owner_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('vquiz_id', sa.Integer(), sa.ForeignKey('vquiz.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('folder_id', sa.Integer(), sa.ForeignKey('quiz_folder.id', ondelete='CASCADE'), nullable=False))
    op.create_index(op.f('ix_quiz_placement_folder_id'), 'quiz_placement', ['folder_id'])


def downgrade():
    #their indexes go with them (MySQL won't drop an index a foreign key still needs)
    op.drop_table('quiz_placement')
    op.drop_table('quiz_folder')
