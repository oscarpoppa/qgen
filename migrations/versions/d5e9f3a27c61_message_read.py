"""Each teacher's own read and cleared state for students' messages and teacher notices

Revision ID: d5e9f3a27c61
Revises: c7d1a5e38b24
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa


revision = 'd5e9f3a27c61'
down_revision = 'c7d1a5e38b24'
branch_labels = None
depends_on = None


def upgrade():
    read = op.create_table(
        'message_read',
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('cleared', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['message_id'], ['message.id'], name='fk_message_read_message', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_message_read_user', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('message_id', 'user_id'),
    )
    op.create_index('ix_message_read_user_id', 'message_read', ['user_id'])
    #keep today's state: whatever teachers have already seen counts as seen by every
    #current teacher (so nobody gets a burst of old alerts)
    message = sa.table('message', sa.column('id', sa.Integer), sa.column('from_teacher', sa.Boolean),
                       sa.column('seen_by_teacher', sa.Boolean))
    user = sa.table('user', sa.column('id', sa.Integer), sa.column('is_admin', sa.Boolean))
    #every such message paired with every teacher
    seen = sa.select(message.c.id, user.c.id, sa.false()) \
        .select_from(message.join(user, sa.true())) \
        .where(message.c.from_teacher.is_(False), message.c.seen_by_teacher.is_(True), user.c.is_admin.is_(True))
    op.execute(read.insert().from_select(['message_id', 'user_id', 'cleared'], seen))


def downgrade():
    #(dropping the table drops its index; MySQL won't drop it first, as a foreign key uses it)
    op.drop_table('message_read')
