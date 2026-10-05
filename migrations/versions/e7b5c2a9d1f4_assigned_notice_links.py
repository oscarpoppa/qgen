"""Teachers' "X assigned ..." notices open what was assigned (a student's copy of the quiz,
or with several students the quiz's results), not the quiz itself: fix the existing ones

Revision ID: e7b5c2a9d1f4
Revises: d4a2e8c1f6b3
Create Date: 2026-10-05

"""
import re
from alembic import op
import sqlalchemy as sa


revision = 'e7b5c2a9d1f4'
down_revision = 'd4a2e8c1f6b3'
branch_labels = None
depends_on = None

BODY = re.compile(r' assigned ".*" to (\d+) students?: (.*?)\.(?: |$)')


def upgrade():
    conn = op.get_bind()
    message = sa.table('message', sa.column('id', sa.Integer), sa.column('kind', sa.String), sa.column('from_teacher', sa.Boolean),
                       sa.column('body', sa.Text), sa.column('link', sa.String), sa.column('created', sa.DateTime))
    user = sa.table('user', sa.column('id', sa.Integer), sa.column('username', sa.String), sa.column('is_admin', sa.Boolean))
    cquiz = sa.table('cquiz', sa.column('id', sa.Integer), sa.column('vquiz_id', sa.Integer), sa.column('assignee', sa.Integer),
                     sa.column('create_date', sa.DateTime))
    rows = conn.execute(sa.select(message.c.id, message.c.body, message.c.link, message.c.created)
                        .where(message.c.kind == 'notice', message.c.from_teacher.is_(False),
                               message.c.link.like('/quiz/listvq/%')).order_by(message.c.id)).fetchall()
    used = {}  # (quiz, person) -> their copies already matched to a notice
    for mid, body, link, created in rows:
        found = BODY.search(body or '')
        tail = link.rsplit('/', 1)[-1]
        if not found or not tail.isdigit():
            continue
        vqid = int(tail)
        new = '/quiz/results/{}'.format(vqid)
        if found.group(1) == '1':
            person = conn.execute(sa.select(user.c.id, user.c.is_admin).where(user.c.username == found.group(2))).first()
            if person is None:
                continue  # the account is gone: leave the link as it was
            if person.is_admin:
                new = '/quiz/listuser/{}'.format(person.id)
            else:
                #their copy made for that assignment: the one made closest to the notice
                #(oldest first on a tie), not one already matched to an earlier notice
                copies = conn.execute(sa.select(cquiz.c.id, cquiz.c.create_date)
                                      .where(cquiz.c.vquiz_id == vqid, cquiz.c.assignee == person.id)
                                      .order_by(cquiz.c.id)).fetchall()
                taken = used.setdefault((vqid, person.id), set())
                free = [c for c in copies if c.id not in taken]
                if not free:
                    continue  # deleted (archived) since: leave it
                far = lambda c: abs((c.create_date - created).total_seconds()) if c.create_date and created else 0
                copy = min(free, key=lambda c: (far(c), c.id))
                taken.add(copy.id)
                new = '/quiz/take/{}'.format(copy.id)
        conn.execute(message.update().where(message.c.id == mid).values(link=new))


def downgrade():
    pass  # the old links only led to the quiz itself; nothing to undo
