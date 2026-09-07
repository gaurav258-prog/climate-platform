"""supervisor_settings: per-regulator supervision profile + overrides (configuration, not code).

A regulator organization picks a profile (its customer class — banking, insurance, markets, agri-food,
integrated) from data/reference/supervision_profiles.json and may override default scenario/horizon and the
supervisory-expectation thresholds per sector metric. One row per regulator org; absent row = registry default.

Revision ID: sup_settings_20260907
Revises: sup_site_access_20260907
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_settings_20260907"
down_revision: Union[str, None] = "sup_site_access_20260907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_settings (
            org_id            UUID PRIMARY KEY REFERENCES organizations(org_id) ON DELETE CASCADE,
            profile           TEXT NOT NULL,
            default_scenario  TEXT,
            default_horizon   TEXT,
            thresholds        JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by        UUID
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervisor_settings")
