"""Pictures and other files can be moved to the Trash: upload_file.removed_at (the owner, 2026-10-26, To do 66)

Revision ID: c4e7a1d9b2f6
Revises: b8e4f2a6d3c1
Create Date: 2026-10-26

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4e7a1d9b2f6'
down_revision = 'b8e4f2a6d3c1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('upload_file') as batch_op:
        batch_op.add_column(sa.Column('removed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('upload_file') as batch_op:
        batch_op.drop_column('removed_at')
