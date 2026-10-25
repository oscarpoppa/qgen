"""Grades changed after a quiz was finished (the owner, 2026-10-25, CP9): who changed them and when, for the
"Grades changed by … on …" line on the results.

Revision ID: b8e4f2a6d3c1
Revises: a7d3e9f1c2b4
Create Date: 2026-10-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8e4f2a6d3c1'
down_revision = 'a7d3e9f1c2b4'
branch_labels = None
depends_on = None


def upgrade():
    #(plain ADD COLUMN, not a batch: see a7d3e9f1c2b4)
    op.add_column('cquiz', sa.Column('changed_by', sa.Integer(), nullable=True))
    op.add_column('cquiz', sa.Column('changed_date', sa.DateTime(), nullable=True))
    #(the link to the person, where the database can add one to a table that's there: MySQL; SQLite can't, 2026-10-25)
    if op.get_bind().dialect.name != 'sqlite':
        op.create_foreign_key('fk_cquiz_changed_by', 'cquiz', 'user', ['changed_by'], ['id'], ondelete='SET NULL')


def downgrade():
    if op.get_bind().dialect.name != 'sqlite':
        op.drop_constraint('fk_cquiz_changed_by', 'cquiz', type_='foreignkey')
    op.drop_column('cquiz', 'changed_date')
    op.drop_column('cquiz', 'changed_by')
