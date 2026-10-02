"""A quiz with a future start time: whether its student has been told it's open

Revision ID: c7a1e4b9d2f3
Revises: b3e7f1d29c84
Create Date: 2026-10-02

"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = 'c7a1e4b9d2f3'
down_revision = 'b3e7f1d29c84'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cquiz') as batch:
        batch.add_column(sa.Column('open_notice_sent', sa.Boolean(), nullable=False, server_default=sa.false()))
    #attempts with no start time, or whose start time has already passed, have nothing to
    #announce: only quizzes still waiting to open get the notice when they do
    op.execute(sa.text('UPDATE cquiz SET open_notice_sent = :yes WHERE opens_at IS NULL OR opens_at <= :now')
               .bindparams(yes=True, now=datetime.now()))


def downgrade():
    with op.batch_alter_table('cquiz') as batch:
        batch.drop_column('open_notice_sent')
