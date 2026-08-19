"""Forward-risk decisions — the 'Act' step of Sense→Score→Project→Act.

When the projection shows an exposure crossing into High+ risk by a horizon, a credit officer / PM /
underwriter records a DECISION on it — reprice, engage the counterparty, disclose, keep monitoring, or
formally accept — with a rationale. The table is the audit trail (who decided what, when, under which
scenario/horizon); the latest row per (entity, scenario, horizon) is the current standing.

Revision ID: risk_decision_202608
Revises: email_outbox_202608
"""
from alembic import op

revision = "risk_decision_202608"
down_revision = "email_outbox_202608"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS risk_decision (
    decision_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES organizations(org_id),
    entity_id    UUID NOT NULL,          -- portfolio_entities.entity_id (no FK — decoupled from the vertical tables)
    entity_name  TEXT,                   -- denormalised so the audit log survives book changes
    scenario     TEXT NOT NULL,
    horizon      TEXT NOT NULL,
    action       TEXT NOT NULL CHECK (action IN ('reprice','engage','disclose','monitor','accept')),
    rationale    TEXT,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','void')),
    decided_by   UUID REFERENCES users(user_id),
    decided_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_risk_decision_lookup ON risk_decision(org_id, entity_id, scenario, horizon, decided_at DESC);
"""

DROP = "DROP TABLE IF EXISTS risk_decision;"


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute(DROP)
