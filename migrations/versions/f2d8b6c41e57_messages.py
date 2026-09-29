"""messages: teacher/student conversations, announcements and automatic notices

Revision ID: f2d8b6c41e57
Revises: e7c4a1d90b25
Create Date: 2026-09-29

"""
from alembic import op
import sqlalchemy as sa


revision = 'f2d8b6c41e57'
down_revision = 'e7c4a1d90b25'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('message',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=True),
        sa.Column('from_teacher', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('kind', sa.String(length=16), nullable=False, server_default='message'),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('link', sa.String(length=256), nullable=True),
        sa.Column('created', sa.DateTime(), nullable=False),
        sa.Column('seen_by_student', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('seen_by_teacher', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['student_id'], ['user.id'], name='fk_message_student_user', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['user.id'], name='fk_message_sender_user', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_message_student_created', 'message', ['student_id', 'created'])


def downgrade():
    op.drop_index('ix_message_student_created', table_name='message')
    op.drop_table('message')
