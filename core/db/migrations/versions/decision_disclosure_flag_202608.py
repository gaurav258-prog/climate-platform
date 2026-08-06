"""Disclosure flags — an approved 'disclose' decision flags the exposure for attention in the next climate
filing, so the reporting team sees, in the cockpit, which exposures Risk wants surfaced this period.

Revision ID: decision_disclosure_flag_202608
Revises: decision_playbook_202608
"""
from alembic import op

revision = "decision_disclosure_flag_202608"
down_revision = "decision_playbook_202608"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE IF NOT EXISTS decision_disclosure_flag (
    flag_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES organizations(org_id),
    entity_id    UUID NOT NULL,
    entity_name  TEXT,
    scenario     TEXT,
    horizon      TEXT,
    decision_id  UUID,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','included','dismissed')),
    flagged_by   UUID REFERENCES users(user_id),
    flagged_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_by  UUID REFERENCES users(user_id),
    resolved_at  TIMESTAMPTZ
);
-- one live flag per exposure
CREATE UNIQUE INDEX IF NOT EXISTS ux_disclosure_flag_open ON decision_disclosure_flag(org_id, entity_id) WHERE status = 'open';
"""

DOWN = "DROP TABLE IF EXISTS decision_disclosure_flag;"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
