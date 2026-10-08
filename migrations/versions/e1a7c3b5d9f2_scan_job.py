"""Workbook pages being turned into problems and quizzes (Scan workbook pages): the AI's
reading and the teacher's edits, kept until Save or Discard

Revision ID: e1a7c3b5d9f2
Revises: d5e9f3a7b2c8
Create Date: 2026-10-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'e1a7c3b5d9f2'
down_revision = 'd5e9f3a7b2c8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scan_job',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('pages', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('data', sa.Text().with_variant(mysql.LONGTEXT(), 'mysql'), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_scan_job_author_id', 'scan_job', ['author_id'])


def downgrade():
    #its index goes with it (MySQL won't drop the index first: the foreign key needs it)
    op.drop_table('scan_job')
