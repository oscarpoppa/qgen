"""Folders for uploaded pictures and other files (the owner, 2026-10-19): a row per upload, and
picture / file folders like the problem and quiz folders.

Revision ID: c8f1d2a7e4b9
Revises: b2e6c8a4d1f7
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision = 'c8f1d2a7e4b9'
down_revision = 'b2e6c8a4d1f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('upload_file',
        sa.Column('id', sa.Integer(), nullable=False),
        #(191: a unique index fits on MySQL utf8mb4 even with the old COMPACT rows, 767 bytes)
        sa.Column('name', sa.String(length=191), nullable=False),
        sa.Column('picture', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('create_date', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'))
    for group in ('picgroup', 'filegroup'):
        op.create_table(group,
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=64), nullable=True),
            sa.Column('summary', sa.String(length=256), nullable=True),
            sa.Column('parent_id', sa.Integer(), nullable=True),
            sa.Column('create_date', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['parent_id'], [group + '.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('title', name='uq_{}_title'.format(group)))
        op.create_index('ix_{}_parent_id'.format(group), group, ['parent_id'])
        op.create_table('upload_' + group,
            sa.Column('upload_id', sa.Integer(), nullable=False),
            sa.Column(group + '_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['upload_id'], ['upload_file.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint([group + '_id'], [group + '.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('upload_id', group + '_id', name='uq_upload_{}'.format(group)))


def downgrade():
    for group in ('filegroup', 'picgroup'):
        op.drop_table('upload_' + group)
        op.drop_index('ix_{}_parent_id'.format(group), table_name=group)
        op.drop_table(group)
    op.drop_table('upload_file')
