"""Regulatory-change register — track a rule change from spotted to shipped.

A new or amended regulation moves through a change process: monitored → analysed → prioritised/scheduled →
built → tested → released. This adds a register so each change is visible with its framework, citation,
impact, effective date, owner (platform vs tenant) and current stage — the "change the bank" pipeline.

Revision ID: reg_changes_20260803
Revises: rconnect_20260803
"""
from alembic import op

revision = "reg_changes_20260803"
down_revision = "rconnect_20260803"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS regulatory_change (
    change_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID REFERENCES organizations(org_id),   -- NULL = platform-wide change
    title          TEXT NOT NULL,
    framework      TEXT,
    summary        TEXT,
    citation       TEXT,
    stage          TEXT NOT NULL DEFAULT 'identified'
                    CHECK (stage IN ('identified','analysis','scheduled','in_dev','testing','released')),
    owner          TEXT NOT NULL DEFAULT 'platform' CHECK (owner IN ('platform','tenant')),
    impact         TEXT,
    effective_date DATE,
    created_by     UUID REFERENCES users(user_id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_reg_change_stage ON regulatory_change (stage);
CREATE INDEX IF NOT EXISTS ix_reg_change_org   ON regulatory_change (org_id);
"""

GUARD = """
CREATE OR REPLACE FUNCTION touch_change_updated() RETURNS trigger AS $$
BEGIN NEW.updated_at := now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_change_touch ON regulatory_change;
CREATE TRIGGER trg_change_touch BEFORE UPDATE ON regulatory_change
    FOR EACH ROW EXECUTE FUNCTION touch_change_updated();
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute(GUARD)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_change_touch ON regulatory_change")
    op.execute("DROP FUNCTION IF EXISTS touch_change_updated()")
    op.execute("DROP TABLE IF EXISTS regulatory_change")
