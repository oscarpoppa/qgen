"""Subjects for problems and quizzes; archive of deleted attempts

The old hidden "Archive" problem and quiz groups (every item was put in them, nothing
showed them) are removed, so everything starts with no subject; the group tables are
now the teacher's Subjects. Deleted attempts are kept in archived_attempt.

Revision ID: e3b7c9d14a58
Revises: d5e9f3a27c61
Create Date: 2026-10-01

"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'e3b7c9d14a58'
down_revision = 'd5e9f3a27c61'
branch_labels = None
depends_on = None

LongText = sa.Text().with_variant(mysql.LONGTEXT(), 'mysql')

#(link table, item column, item table, group column, group table)
LINKS = [('vproblem_vpgroup', 'vproblem_id', 'vproblem', 'vpgroup_id', 'vpgroup'),
         ('vquiz_vqgroup', 'vquiz_id', 'vquiz', 'vqgroup_id', 'vqgroup')]


def upgrade():
    for link, item_col, _item, group_col, group in LINKS:
        groups = sa.table(group, sa.column('id', sa.Integer), sa.column('title', sa.String))
        links = sa.table(link, sa.column(item_col, sa.Integer), sa.column(group_col, sa.Integer))
        archive_ids = sa.select(groups.c.id).where(groups.c.title == 'Archive')
        op.execute(links.delete().where(links.c[group_col].in_(archive_ids)))
        op.execute(groups.delete().where(groups.c.title == 'Archive'))
        op.execute(links.delete().where(sa.or_(links.c[item_col].is_(None), links.c[group_col].is_(None))))
        with op.batch_alter_table(link) as batch:
            batch.alter_column(item_col, existing_type=sa.Integer(), nullable=False)
            batch.alter_column(group_col, existing_type=sa.Integer(), nullable=False)
            batch.create_unique_constraint('uq_' + link, [item_col, group_col])
        with op.batch_alter_table(group) as batch:
            batch.create_unique_constraint('uq_{}_title'.format(group), ['title'])

    op.create_table(
        'archived_attempt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('original_id', sa.Integer(), nullable=False),
        sa.Column('vquiz_id', sa.Integer(), nullable=True),
        sa.Column('student_id', sa.Integer(), nullable=True),
        sa.Column('student_name', sa.String(length=64), nullable=False),
        sa.Column('quiz_title', sa.String(length=64), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('completed', sa.Boolean(), nullable=False),
        sa.Column('needs_review', sa.Boolean(), nullable=False),
        sa.Column('startdate', sa.DateTime(), nullable=True),
        sa.Column('compdate', sa.DateTime(), nullable=True),
        sa.Column('assigned', sa.DateTime(), nullable=True),
        sa.Column('archived_at', sa.DateTime(), nullable=False),
        sa.Column('archived_by', sa.Integer(), nullable=True),
        sa.Column('problem_ids', sa.Text(), nullable=False),
        sa.Column('reason', sa.String(length=16), nullable=False),
        sa.Column('results_html', LongText, nullable=False),
        sa.Column('data', LongText, nullable=False),
        sa.ForeignKeyConstraint(['vquiz_id'], ['vquiz.id'], name='fk_archived_attempt_vquiz', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['student_id'], ['user.id'], name='fk_archived_attempt_student', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['archived_by'], ['user.id'], name='fk_archived_attempt_archiver', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_archived_attempt_archived_at', 'archived_attempt', ['archived_at'])
    op.create_index('ix_archived_attempt_student_id', 'archived_attempt', ['student_id'])
    op.create_index('ix_archived_attempt_vquiz_id', 'archived_attempt', ['vquiz_id'])


def downgrade():
    #(dropping the table drops its indexes; MySQL won't drop them first, as foreign keys use them)
    op.drop_table('archived_attempt')
    for link, item_col, item, group_col, group in LINKS:
        with op.batch_alter_table(group) as batch:
            batch.drop_constraint('uq_{}_title'.format(group), type_='unique')
        with op.batch_alter_table(link) as batch:
            batch.drop_constraint('uq_' + link, type_='unique')
            batch.alter_column(item_col, existing_type=sa.Integer(), nullable=True)
            batch.alter_column(group_col, existing_type=sa.Integer(), nullable=True)
        #back to before: every problem (quiz) in one "Archive" group, and nothing else
        groups = sa.table(group, sa.column('id', sa.Integer), sa.column('title', sa.String),
                          sa.column('create_date', sa.DateTime))
        links = sa.table(link, sa.column(item_col, sa.Integer), sa.column(group_col, sa.Integer))
        items = sa.table(item, sa.column('id', sa.Integer))
        op.execute(links.delete())
        op.execute(groups.delete())
        op.execute(groups.insert().values(title='Archive', create_date=datetime.now()))
        archive_id = sa.select(groups.c.id).where(groups.c.title == 'Archive').scalar_subquery()
        op.execute(links.insert().from_select([item_col, group_col], sa.select(items.c.id, archive_id)))
