"""Immutable ESRS/CSRD report snapshots — freeze an as-of filing.

A disclosure that is filed or handed to an assurer must be reproducible: the exact figures, the exact
reporting basis (scenario, horizon, materiality, period), the exact golden-source state — frozen and
versioned, never silently recomputed. This is the audit spine under a filing: you can always show the
board or the auditor the very bytes that were signed off, even after the live engine has moved on.

Append-only by construction: a snapshot row is written once and never updated or deleted (no UPDATE/DELETE
path in the service). A correction is a NEW version, so the history is complete. Versions are per
(org, report_type), monotonically increasing.

Revision ID: report_snapshots_20260730
Revises: org_reporting_settings_20260730
"""
from alembic import op

revision = "report_snapshots_20260730"
down_revision = "org_reporting_settings_20260730"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS report_snapshots (
            snapshot_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            report_type     TEXT NOT NULL,
            version         INTEGER NOT NULL,
            reporting_basis JSONB NOT NULL,
            payload         JSONB NOT NULL,
            note            TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by      UUID REFERENCES users(user_id),
            UNIQUE (org_id, report_type, version)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_report_snapshots_org_type "
               "ON report_snapshots (org_id, report_type, version DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS report_snapshots")
