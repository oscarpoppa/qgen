"""archived people: user.archived_at (the trash can's Move to Archive, 2026-10-16)

Revision ID: c4e9a1b7d2f6
Revises: b8d2f4a6c1e3
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4e9a1b7d2f6'
down_revision = 'b8d2f4a6c1e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch:
        batch.add_column(sa.Column('archived_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('archived_folders', sa.Text(), nullable=True))
        batch.create_index('ix_user_archived_at', ['archived_at'])


def downgrade():
    with op.batch_alter_table('user') as batch:
        batch.drop_index('ix_user_archived_at')
        batch.drop_column('archived_folders')
        batch.drop_column('archived_at')
