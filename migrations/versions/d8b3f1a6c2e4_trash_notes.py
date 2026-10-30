"""The message written when something goes to the Trash, sent in the notice and kept with it there (the owner, 2026-10-29)

Revision ID: d8b3f1a6c2e4
Revises: c4a9e2f7d1b3
Create Date: 2026-10-29

"""
from alembic import op
import sqlalchemy as sa


revision = 'd8b3f1a6c2e4'
down_revision = 'c4a9e2f7d1b3'
branch_labels = None
depends_on = None


def upgrade():
    #(a new table only: nothing is rebuilt, so nothing cascades)
    op.create_table(
        'trash_note',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('by_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.Column('changed_by_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('changed_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('kind', 'item_id', name='uq_trash_note_item'))


def downgrade():
    op.drop_table('trash_note')
