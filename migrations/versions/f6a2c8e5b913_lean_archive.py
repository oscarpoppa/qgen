"""Archived attempts keep a compact JSON record only (no saved results page)

The results page of an archived attempt is drawn from its record when looked at, so the
copy of the page (results_html) and the copy inside the record (the attempt's saved
transcript) are dropped. Each question in the record also notes its question type and
picture (format 2), so it reads right even after the problem is deleted. Results saved
before the upgrade (old format) keep their old page: it's their only record.

Revision ID: f6a2c8e5b913
Revises: e3b7c9d14a58
Create Date: 2026-10-01

"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'f6a2c8e5b913'
down_revision = 'e3b7c9d14a58'
branch_labels = None
depends_on = None

LongText = sa.Text().with_variant(mysql.LONGTEXT(), 'mysql')
TRANSCRIPT_V2 = '<!--transcript v2-->'


def upgrade():
    bind = op.get_bind()
    archived = sa.table('archived_attempt', sa.column('id', sa.Integer), sa.column('vquiz_id', sa.Integer),
                        sa.column('data', sa.Text))
    vproblem = sa.table('vproblem', sa.column('id', sa.Integer), sa.column('qtype', sa.String),
                        sa.column('image', sa.String))
    vquiz = sa.table('vquiz', sa.column('id', sa.Integer), sa.column('image', sa.String))
    problems = {r.id: r for r in bind.execute(sa.select(vproblem.c.id, vproblem.c.qtype, vproblem.c.image))}
    quiz_images = {r.id: r.image for r in bind.execute(sa.select(vquiz.c.id, vquiz.c.image))}
    for row in bind.execute(sa.select(archived.c.id, archived.c.vquiz_id, archived.c.data)).fetchall():
        record = json.loads(row.data)
        attempt = record.get('attempt') or {}
        if (attempt.get('transcript') or '').startswith(TRANSCRIPT_V2):
            attempt['transcript'] = TRANSCRIPT_V2
        for p in record.get('problems') or []:
            vp = problems.get(p.get('vproblem_id'))
            p.setdefault('qtype', vp.qtype if vp else 'numeric')
            p.setdefault('problem_image', vp.image if vp else None)
        record.setdefault('quiz_image', quiz_images.get(row.vquiz_id))
        record['v'] = 2
        bind.execute(archived.update().where(archived.c.id == row.id)
                     .values(data=json.dumps(record, separators=(',', ':'), ensure_ascii=False)))
    with op.batch_alter_table('archived_attempt') as batch:
        batch.drop_column('results_html')


def downgrade():
    #the older version showed a saved page; records stay complete (and restorable), but
    #the page itself isn't rebuilt here
    with op.batch_alter_table('archived_attempt') as batch:
        batch.add_column(sa.Column('results_html', LongText, nullable=True))
    archived = sa.table('archived_attempt', sa.column('results_html', sa.Text))
    op.execute(archived.update().values(
        results_html='<div class="card"><p>This archived attempt can be restored to see its results.</p></div>'))
    with op.batch_alter_table('archived_attempt') as batch:
        batch.alter_column('results_html', existing_type=LongText, nullable=False)
