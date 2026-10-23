"""Folders for stashed scans (the owner, 2026-10-23): shared by all teachers, seen only on Scan workbook
pages' Stashed scans card; a folder on each scan (none: Uncategorized).

Revision ID: e5b9c3a1d7f2
Revises: c8f1d2a7e4b9
Create Date: 2026-10-23
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5b9c3a1d7f2'
down_revision = 'c8f1d2a7e4b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('scan_folder',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['scan_folder.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_scan_folder_parent_id', 'scan_folder', ['parent_id'])
    with op.batch_alter_table('scan_job') as batch:
        batch.add_column(sa.Column('folder_id', sa.Integer(), nullable=True))
        batch.create_index('ix_scan_job_folder_id', ['folder_id'])
        batch.create_foreign_key('fk_scan_job_folder', 'scan_folder', ['folder_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('scan_job') as batch:
        batch.drop_constraint('fk_scan_job_folder', type_='foreignkey')
        batch.drop_index('ix_scan_job_folder_id')
        batch.drop_column('folder_id')
    op.drop_index('ix_scan_folder_parent_id', table_name='scan_folder')
    op.drop_table('scan_folder')
