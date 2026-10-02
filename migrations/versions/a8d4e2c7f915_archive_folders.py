"""Archive folders that can be renamed and deleted

Until now the Archive's folders were worked out from student names. Now they are stored
(archive_folder): one per student, made here for every student and for each deleted
account that has archived attempts; archived attempts are filed into them (folder_id;
none means Unsorted).

Revision ID: a8d4e2c7f915
Revises: f6a2c8e5b913
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa


revision = 'a8d4e2c7f915'
down_revision = 'f6a2c8e5b913'
branch_labels = None
depends_on = None


def upgrade():
    folders = op.create_table(
        'archive_folder',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=True),
        sa.Column('removed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['student_id'], ['user.id'], name='fk_archive_folder_student', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', name='uq_archive_folder_student'),
    )
    with op.batch_alter_table('archived_attempt') as batch:
        batch.add_column(sa.Column('folder_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_archived_attempt_folder', 'archive_folder', ['folder_id'], ['id'], ondelete='SET NULL')
        batch.create_index('ix_archived_attempt_folder_id', ['folder_id'])

    bind = op.get_bind()
    user = sa.table('user', sa.column('id', sa.Integer), sa.column('username', sa.String), sa.column('is_admin', sa.Boolean))
    archived = sa.table('archived_attempt', sa.column('id', sa.Integer), sa.column('student_id', sa.Integer),
                        sa.column('student_name', sa.String), sa.column('folder_id', sa.Integer))
    users = {r.id: r for r in bind.execute(sa.select(user.c.id, user.c.username, user.c.is_admin))}
    rows = bind.execute(sa.select(archived.c.id, archived.c.student_id, archived.c.student_name)).fetchall()
    #a folder for every student, and for anyone else (a teacher) with archived attempts
    want = {uid for uid, u in users.items() if not u.is_admin}
    want |= {r.student_id for r in rows if r.student_id in users}
    folder_of = {}
    for uid in sorted(want):
        bind.execute(folders.insert().values(name=users[uid].username, student_id=uid, removed=False))
        folder_of[('user', uid)] = bind.execute(sa.select(folders.c.id).where(folders.c.student_id == uid)).scalar()
    #deleted accounts: one folder per name
    for r in rows:
        if r.student_id in users:
            key = ('user', r.student_id)
        else:
            key = ('gone', r.student_name.lower())
            if key not in folder_of:
                result = bind.execute(folders.insert().values(name=r.student_name, student_id=None, removed=False))
                folder_of[key] = result.inserted_primary_key[0]
        bind.execute(archived.update().where(archived.c.id == r.id).values(folder_id=folder_of[key]))


def downgrade():
    with op.batch_alter_table('archived_attempt') as batch:
        batch.drop_constraint('fk_archived_attempt_folder', type_='foreignkey')
        batch.drop_index('ix_archived_attempt_folder_id')
        batch.drop_column('folder_id')
    op.drop_table('archive_folder')
