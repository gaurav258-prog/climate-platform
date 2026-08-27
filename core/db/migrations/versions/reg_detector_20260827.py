"""Live EUR-Lex change detector — snapshot + detected-change tables.

Backs services/regulatory_monitoring/eurlex_detector.py: `reg_source_snapshot` holds the last-seen legal
signal (entry-into-force dates, in-force, doc date) per framework's governing act; `reg_detected_change`
records a change when that signal moves at the source (pending human review). Idempotent.

Revision ID: reg_detector_20260827
Revises: decision_verb_packs_20260826
"""
from alembic import op

revision = "reg_detector_20260827"
down_revision = "decision_verb_packs_20260826"
branch_labels = None
depends_on = None

_DDL = """
CREATE TABLE IF NOT EXISTS reg_source_snapshot (
  framework   text PRIMARY KEY,
  celex       text NOT NULL,
  fingerprint text NOT NULL,
  signal      jsonb,
  checked_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reg_detected_change (
  change_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  framework      text NOT NULL,
  celex          text NOT NULL,
  title          text NOT NULL,
  summary        text,
  effective_date date,
  status         text NOT NULL DEFAULT 'pending_review',
  url            text,
  detected_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_reg_detected_change_fw ON reg_detected_change (framework, status);
"""


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reg_detected_change; DROP TABLE IF EXISTS reg_source_snapshot;")
