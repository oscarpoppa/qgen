"""Folders inside folders everywhere: the Problems and Quizzes pages' folders and the
Archive's folders can hold folders, like My quizzes and Users

Revision ID: b3e7d1a5c9f2
Revises: a9c4e2f7b1d3
Create Date: 2026-10-06

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3e7d1a5c9f2'
down_revision = 'a9c4e2f7b1d3'
branch_labels = None
depends_on = None

TABLES = ('vpgroup', 'vqgroup', 'archive_folder')


def upgrade():
    #a student's Archive folder the teacher renamed keeps that name (else it follows the username)
    with op.batch_alter_table('archive_folder') as batch:
        batch.add_column(sa.Column('own_name', sa.Boolean(), nullable=False, server_default=sa.false()))
    for t in TABLES:
        with op.batch_alter_table(t) as batch:
            batch.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
            batch.create_index('ix_{}_parent_id'.format(t), ['parent_id'])
            batch.create_foreign_key('fk_{}_parent'.format(t), t, ['parent_id'], ['id'], ondelete='CASCADE')


def downgrade():
    for t in TABLES:
        with op.batch_alter_table(t) as batch:
            batch.drop_constraint('fk_{}_parent'.format(t), type_='foreignkey')
            batch.drop_index('ix_{}_parent_id'.format(t))
            batch.drop_column('parent_id')
    with op.batch_alter_table('archive_folder') as batch:
        batch.drop_column('own_name')
