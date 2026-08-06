"""Decision watchlist — an approved 'monitor' decision puts the exposure on a watchlist with a re-review
date. A scheduled re-check re-scores each watch against the projection it was added under and raises an
alert when the exposure deteriorates further, so 'monitor' is an active control, not a filed-and-forgotten note.

Revision ID: decision_watchlist_202608
Revises: decision_disclosure_flag_202608
"""
from alembic import op

revision = "decision_watchlist_202608"
down_revision = "decision_disclosure_flag_202608"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE IF NOT EXISTS decision_watchlist (
    watch_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(org_id),
    entity_id       UUID NOT NULL,
    entity_name     TEXT,
    scenario        TEXT,
    horizon         TEXT,
    decision_id     UUID,
    baseline_score  DOUBLE PRECISION,          -- the projected High+ score when the watch was opened
    review_date     DATE,                      -- when the re-check is due
    status          TEXT NOT NULL DEFAULT 'watching' CHECK (status IN ('watching','cleared','escalated')),
    last_checked_at TIMESTAMPTZ,
    last_score      DOUBLE PRECISION,          -- most recent re-scored value
    last_delta      DOUBLE PRECISION,          -- last_score - baseline_score (>0 = deteriorated further)
    added_by        UUID REFERENCES users(user_id),
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_by     UUID REFERENCES users(user_id),
    resolved_at     TIMESTAMPTZ
);
-- one live watch per exposure
CREATE UNIQUE INDEX IF NOT EXISTS ux_watchlist_open ON decision_watchlist(org_id, entity_id) WHERE status = 'watching';
"""

DOWN = "DROP TABLE IF EXISTS decision_watchlist;"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
