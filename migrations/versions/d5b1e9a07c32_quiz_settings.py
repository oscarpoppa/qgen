"""quiz settings: retake scoring, answer release, open/close window, time limit, site settings

Revision ID: d5b1e9a07c32
Revises: c3a7d2e41f90
Create Date: 2026-09-29

"""
from alembic import op
import sqlalchemy as sa


revision = 'd5b1e9a07c32'
down_revision = 'c3a7d2e41f90'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vquiz', schema=None) as batch_op:
        batch_op.add_column(sa.Column('retake_rule', sa.String(length=16), nullable=False, server_default='best'))
        batch_op.add_column(sa.Column('hide_answers', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('answers_released', sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table('cquiz', schema=None) as batch_op:
        batch_op.add_column(sa.Column('opens_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('closes_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('time_limit', sa.Integer(), nullable=True))
        #per-student override of the quiz's retake rule (kept on the newest attempt)
        batch_op.add_column(sa.Column('retake_rule', sa.String(length=16), nullable=True))

    op.create_table('setting',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('key'))


def downgrade():
    op.drop_table('setting')
    with op.batch_alter_table('cquiz', schema=None) as batch_op:
        batch_op.drop_column('retake_rule')
        batch_op.drop_column('time_limit')
        batch_op.drop_column('closes_at')
        batch_op.drop_column('opens_at')
    with op.batch_alter_table('vquiz', schema=None) as batch_op:
        batch_op.drop_column('answers_released')
        batch_op.drop_column('hide_answers')
        batch_op.drop_column('retake_rule')
