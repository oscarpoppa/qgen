"""foreign key delete rules (deleting a teacher keeps their problems, quizzes, grades and log); longer quiz lists

Revision ID: e7c4a1d90b25
Revises: d5b1e9a07c32
Create Date: 2026-09-29

"""
from alembic import op
import sqlalchemy as sa


revision = 'e7c4a1d90b25'
down_revision = 'd5b1e9a07c32'
branch_labels = None
depends_on = None

#(table, column): a deleted user leaves these rows in place with the link cleared
LINKS = [('vproblem', 'author_id'), ('vquiz', 'author_id'), ('cquiz', 'graded_by'), ('aicall', 'user_id')]


def _fk_name(bind, table, column):
    for fk in sa.inspect(bind).get_foreign_keys(table):
        if fk['constrained_columns'] == [column] and fk['referred_table'] == 'user':
            return fk['name']
    return None


def _set_rule(rule):
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        #SQLite dev/test databases: foreign keys come from the models; nothing to alter
        return
    for table, column in LINKS:
        name = _fk_name(bind, table, column)
        if name:
            op.drop_constraint(name, table, type_='foreignkey')
        op.create_foreign_key('fk_{}_{}_user'.format(table, column), table, 'user', [column], ['id'], ondelete=rule)


def upgrade():
    _set_rule('SET NULL')
    #a quiz's problem list with groups can be longer than 256 characters
    with op.batch_alter_table('vquiz', schema=None) as batch_op:
        batch_op.alter_column('vpid_lst', existing_type=sa.String(length=256), type_=sa.Text())


def downgrade():
    with op.batch_alter_table('vquiz', schema=None) as batch_op:
        batch_op.alter_column('vpid_lst', existing_type=sa.Text(), type_=sa.String(length=256))
    _set_rule(None)
