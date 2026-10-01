"""API tokens and sign-in throttling, pinned/grouped messages, profile pictures

Revision ID: a9e3f05d7b18
Revises: f2d8b6c41e57
Create Date: 2026-09-30

"""
from alembic import op
import sqlalchemy as sa


revision = 'a9e3f05d7b18'
down_revision = 'f2d8b6c41e57'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('api_token',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        #only a SHA-256 fingerprint is kept; the token itself is shown once
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('prefix', sa.String(length=12), nullable=False),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_api_token_user', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_api_token_token_hash', 'api_token', ['token_hash'], unique=True)

    op.create_table('login_failure',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_login_failure_username_created', 'login_failure', ['username', 'created'])

    with op.batch_alter_table('message', schema=None) as batch_op:
        #an announcement pinned to the top of students' home pages
        batch_op.add_column(sa.Column('pinned', sa.Boolean(), nullable=False, server_default=sa.false()))
        #rows sent together (one broadcast) share this, so they can be pinned or unpinned together
        batch_op.add_column(sa.Column('batch', sa.String(length=32), nullable=True))
        batch_op.create_index('ix_message_batch', ['batch'])

    with op.batch_alter_table('user', schema=None) as batch_op:
        #file name of the profile picture's square thumbnail in the static folder
        batch_op.add_column(sa.Column('avatar', sa.String(length=128), nullable=True))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('avatar')
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.drop_index('ix_message_batch')
        batch_op.drop_column('batch')
        batch_op.drop_column('pinned')
    op.drop_table('login_failure')
    #dropping the table drops its indexes (MySQL won't drop one a foreign key uses first)
    op.drop_table('api_token')
