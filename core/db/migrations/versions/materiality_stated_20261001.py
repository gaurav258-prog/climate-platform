"""org_reporting_settings loses materiality_threshold: a second definition of 'material physical risk' beside the
undertaking's stated at-risk level (method.at_risk_level, attested per financial year — E69), defaulting to the
platform's own 40 and never attested. Every reader now uses the stated level. Reversible: the values are kept in a
side table and the downgrade restores the column (NOT NULL DEFAULT 40, as it was) with them.

Revision ID: materiality_stated_20261001
Revises: geo_prior_levels_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "materiality_stated_20261001"
down_revision: Union[str, None] = "geo_prior_levels_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE org_reporting_settings_retired_20261001 AS
            SELECT org_id, materiality_threshold FROM org_reporting_settings;
        ALTER TABLE org_reporting_settings DROP COLUMN materiality_threshold;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE org_reporting_settings ADD COLUMN materiality_threshold INTEGER NOT NULL DEFAULT 40;
        UPDATE org_reporting_settings s SET materiality_threshold = r.materiality_threshold
        FROM org_reporting_settings_retired_20261001 r WHERE r.org_id = s.org_id;
        DROP TABLE org_reporting_settings_retired_20261001;
    """)
