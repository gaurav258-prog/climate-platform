"""bank_asset_risk_projection_view

Reconciliation step #1: wire the bank vertical onto canonical_scores.

Creates `v_bank_asset_physical_risk`, which projects each bank asset's physical
risk FROM the canonical golden source by H3 cell — the same join the platform's
/v1/scores/portfolio endpoint already uses. Bank reporting should read this view
instead of the stored `climate_hazard_exposure.physical_risk_score`, which is
now deprecated.

Also stamps a deprecation COMMENT on the stored column so it is visible in the
database itself, not just in code.

Revision ID: c8d2b3e4f5a6
Revises: b7c1a2d3e4f5
Create Date: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c8d2b3e4f5a6"
down_revision: Union[str, None] = "b7c1a2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VIEW_SQL = """
CREATE OR REPLACE VIEW v_bank_asset_physical_risk AS
SELECT DISTINCT ON (ba.asset_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       ba.org_id,
       ba.asset_id,
       ba.h3_cell,
       cs.hazard_type,
       cs.scenario,
       cs.time_horizon,
       CAST(cs.risk_score AS NUMERIC(5,2)) AS physical_risk_score,  -- projected, not stored
       cs.risk_bucket,
       cs.model_version,
       cs.scored_at,
       'canonical_scores'::text            AS risk_source
FROM   bank_assets      ba
JOIN   canonical_scores cs ON cs.h3_cell = ba.h3_cell
WHERE  cs.valid_to IS NULL
ORDER  BY ba.asset_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;
"""


def upgrade() -> None:
    op.execute(VIEW_SQL)
    op.execute(
        "COMMENT ON COLUMN climate_hazard_exposure.physical_risk_score IS "
        "'DEPRECATED: project from canonical_scores via v_bank_asset_physical_risk. "
        "Stored value retained only for transition/backfill.'"
    )


def downgrade() -> None:
    op.execute("COMMENT ON COLUMN climate_hazard_exposure.physical_risk_score IS NULL")
    op.execute("DROP VIEW IF EXISTS v_bank_asset_physical_risk")
