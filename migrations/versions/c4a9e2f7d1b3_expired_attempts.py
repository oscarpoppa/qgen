"""Attempts the app handed in by itself because their time ran out or their quiz closed (the gold and blue fish bones),
and whether a teacher has opened each one since (Open Quizzes lists it till then; the owner, 2026-10-29)

Revision ID: c4a9e2f7d1b3
Revises: f3c8d2a6b1e9
Create Date: 2026-10-29

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4a9e2f7d1b3'
down_revision = 'f3c8d2a6b1e9'
branch_labels = None
depends_on = None


def upgrade():
    #(attempts handed in before this can't be told apart: none of them is marked)
    #(add_column only: on SQLite that's a plain ALTER, no rebuild of cquiz, so its cproblems are safe)
    op.add_column('cquiz', sa.Column('expired', sa.String(8), nullable=True))
    op.add_column('cquiz', sa.Column('expired_seen', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    #(on SQLite this rebuilds cquiz, and the rebuild's DROP cascades to every attempt's cproblems: the sandbox lost
    #147 on 2026-10-29. Put the backup taken before the upgrade back instead of running this there.)
    with op.batch_alter_table('cquiz') as batch:
        batch.drop_column('expired_seen')
        batch.drop_column('expired')
