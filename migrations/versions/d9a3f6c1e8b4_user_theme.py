"""Each person's color theme, picked on My profile: user.theme (the owner, 2026-10-26, To do 64)

Revision ID: d9a3f6c1e8b4
Revises: c4e7a1d9b2f6
Create Date: 2026-10-26

"""
from alembic import op
import sqlalchemy as sa


revision = 'd9a3f6c1e8b4'
down_revision = 'c4e7a1d9b2f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('theme', sa.String(length=16), nullable=True))


def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('theme')
