"""question types, saved answers, instructor review, shuffled question order, AI call log

Revision ID: c3a7d2e41f90
Revises: 95f1e890c9dd
Create Date: 2026-09-29

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3a7d2e41f90'
down_revision = '95f1e890c9dd'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vproblem', schema=None) as batch_op:
        batch_op.add_column(sa.Column('qtype', sa.String(length=32), nullable=False, server_default='numeric'))
        batch_op.add_column(sa.Column('options', sa.Text(), nullable=True))
        batch_op.alter_column('raw_ansr', existing_type=sa.String(length=128), type_=sa.Text())

    with op.batch_alter_table('cproblem', schema=None) as batch_op:
        batch_op.add_column(sa.Column('conc_opts', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('submitted', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('credit', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('feedback', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('highlights', sa.Text(), nullable=True))
        batch_op.alter_column('conc_ansr', existing_type=sa.String(length=128), type_=sa.Text())

    with op.batch_alter_table('vquiz', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shuffle_order', sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table('cquiz', schema=None) as batch_op:
        batch_op.add_column(sa.Column('needs_review', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('graded_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('graded_date', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key('fk_cquiz_graded_by_user', 'user', ['graded_by'], ['id'])
        batch_op.alter_column('transcript', existing_type=sa.String(length=8192), type_=sa.Text())

    op.create_table('aicall',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created', sa.DateTime(), nullable=True),
        sa.Column('kind', sa.String(length=16), nullable=True),
        sa.Column('request', sa.Text(), nullable=True),
        sa.Column('ok', sa.Boolean(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_aicall_created', 'aicall', ['created'])

    #existing problems keep working exactly as before through the old markup path
    op.execute("""UPDATE vproblem SET options = '{"markup": "legacy"}'""")
    #the one 'selone' test problem from the sandbox branch expects a typed letter
    op.execute("UPDATE vproblem SET qtype = 'text' WHERE form_elem = 'selone'")


def downgrade():
    op.drop_index('ix_aicall_created', table_name='aicall')
    op.drop_table('aicall')
    with op.batch_alter_table('cquiz', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cquiz_graded_by_user', type_='foreignkey')
        batch_op.drop_column('graded_date')
        batch_op.drop_column('graded_by')
        batch_op.drop_column('needs_review')
    with op.batch_alter_table('vquiz', schema=None) as batch_op:
        batch_op.drop_column('shuffle_order')
    with op.batch_alter_table('cproblem', schema=None) as batch_op:
        batch_op.drop_column('highlights')
        batch_op.drop_column('feedback')
        batch_op.drop_column('credit')
        batch_op.drop_column('submitted')
        batch_op.drop_column('conc_opts')
    with op.batch_alter_table('vproblem', schema=None) as batch_op:
        batch_op.drop_column('options')
        batch_op.drop_column('qtype')
