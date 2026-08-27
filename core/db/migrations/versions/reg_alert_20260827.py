"""CRCS · proactive-alert dedup table.

Backs services/governance/reg_alerts.py: one row per alert already raised for an org (unique on org_id +
alert_key), so the daily sweep notifies once per detected change / approaching deadline. Idempotent.

Revision ID: reg_alert_20260827
Revises: reg_detector_20260827
"""
from alembic import op

revision = "reg_alert_20260827"
down_revision = "reg_detector_20260827"
branch_labels = None
depends_on = None

_DDL = """
CREATE TABLE IF NOT EXISTS reg_alert (
  alert_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         uuid NOT NULL,
  alert_key      text NOT NULL,
  framework      text,
  kind           text NOT NULL,
  title          text NOT NULL,
  effective_date date,
  task_id        uuid,
  raised_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, alert_key)
);
"""


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reg_alert;")
