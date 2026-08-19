"""Email outbox — a durable transactional outbox for outbound notification email.

An email is queued in the SAME transaction as the event that triggers it (e.g. a task @mention), so it is
never lost and never sent for a rolled-back action. A best-effort delivery pass runs inline; whatever is left
'pending' or 'failed' is safely retriable by a worker. The rendered subject/body are stored, so delivery can
happen later (once SMTP is configured) without reconstructing anything.

Revision ID: email_outbox_202608
Revises: reg_task_attach_mention_202608
"""
from alembic import op

revision = "email_outbox_202608"
down_revision = "reg_task_attach_mention_202608"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS email_outbox (
    outbox_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID REFERENCES organizations(org_id),
    to_email    TEXT NOT NULL,
    subject     TEXT NOT NULL,
    body_html   TEXT,
    body_text   TEXT,
    kind        TEXT,                 -- e.g. 'task_mention'
    ref_type    TEXT,                 -- what this email is about, for idempotency / lookup
    ref_id      UUID,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','sent','failed','skipped')),
    transport   TEXT,                 -- which transport handled it (smtp / console / off)
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_email_outbox_pending ON email_outbox(status, created_at);
"""

DROP = "DROP TABLE IF EXISTS email_outbox;"


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute(DROP)
