"""assetmgmt_holdings

Asset Management is the platform's 5th vertical -- "Portfolio climate VaR and
screening." Unlike Real Estate (which needed one new scoring module), this
vertical needs zero new scoring code: "climate VaR%" is the exact same
recommended_discount_pct()/valuation_block() haircut-by-bucket schedule from
ml/scoring/valuation_discount.py already used for banking's collateral
haircut and real estate's climate-adjusted value, relabeled a third time --
the sharpest demonstration yet that this is one engine, not four products.

Same shape as bank_assets/insurance_policies/realestate_properties/
sc_sourcing_plots: an org-scoped table + a view projecting canonical_scores
by H3 cell. nace_code is included directly here (unlike banking/real estate's
current upload gap) since an asset manager's own holdings data typically
already carries a NACE classification.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE IF NOT EXISTS assetmgmt_holdings (
    holding_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    holding_name       VARCHAR(160) NOT NULL,
    sector             VARCHAR(100),
    nace_code          VARCHAR(10),
    latitude           DOUBLE PRECISION,
    longitude          DOUBLE PRECISION,
    h3_cell            VARCHAR(20),
    country            VARCHAR(2),
    region             VARCHAR(80),
    position_value_eur NUMERIC(18,2) NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_assetmgmt_holdings_org ON assetmgmt_holdings(org_id);
CREATE INDEX IF NOT EXISTS ix_assetmgmt_holdings_h3  ON assetmgmt_holdings(h3_cell);

CREATE OR REPLACE VIEW v_assetmgmt_holding_physical_risk AS
SELECT DISTINCT ON (h.holding_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       h.org_id, h.holding_id, h.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   assetmgmt_holdings h
JOIN   canonical_scores   cs ON cs.h3_cell = h.h3_cell AND cs.valid_to IS NULL
ORDER  BY h.holding_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;
"""

DOWNGRADE = """
DROP VIEW IF EXISTS v_assetmgmt_holding_physical_risk;
DROP TABLE IF EXISTS assetmgmt_holdings;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
