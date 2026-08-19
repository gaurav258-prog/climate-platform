"""Per-org reporting basis — configurable so the Omnibus reshuffle doesn't need code edits.

Reporting period, scenario, horizon and the ESRS materiality threshold are legitimate reporting-policy
choices a compliance officer sets; they must not be hardcoded constants. (The r²≥0.40 publish gate is
deliberately NOT here — it is an honesty/scientific constant, not an org knob.)

Revision ID: org_reporting_settings_20260730
Revises: platform_admin_perm_20260730
"""
from alembic import op

revision = "org_reporting_settings_20260730"
down_revision = "platform_admin_perm_20260730"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS org_reporting_settings (
            org_id               UUID PRIMARY KEY REFERENCES organizations(org_id) ON DELETE CASCADE,
            reporting_period_end DATE,
            scenario             TEXT NOT NULL DEFAULT 'baseline',
            horizon              TEXT NOT NULL DEFAULT 'current',
            materiality_threshold INTEGER NOT NULL DEFAULT 40,
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by           UUID REFERENCES users(user_id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS org_reporting_settings")
