"""insurance_underwriting_book

Insurance's "Loss-curve pricing" workflow was a UI placeholder (catalog.js
service.workflow=null) with no backing data -- unlike banking (bank_assets)
and agriculture (sc_sourcing_plots), the insurer had a login and tenant scope
but nothing to project risk onto. This adds insurance_policies (Iberia
Mutual's property book) and a projection view onto canonical_scores, the same
shape as bank_assets/v_bank_asset_physical_risk and
sc_sourcing_plots/v_sc_plot_physical_risk -- three verticals, one golden
source, three different projections.

Revision ID: 9f8e7d6c5b4a
Revises: c4d5e6f7a8b9
Create Date: 2026-07-04

"""
from typing import Sequence, Union

from alembic import op

revision: str = "9f8e7d6c5b4a"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE IF NOT EXISTS insurance_policies (
    policy_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    policy_name      VARCHAR(160) NOT NULL,
    policy_type      VARCHAR(40) NOT NULL DEFAULT 'property',
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    h3_cell          VARCHAR(20),
    country          VARCHAR(2),
    region           VARCHAR(80),
    sum_insured_eur  NUMERIC(16,2) NOT NULL,
    deductible_pct   NUMERIC(5,4) NOT NULL DEFAULT 0.02,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_insurance_policies_org ON insurance_policies(org_id);
CREATE INDEX IF NOT EXISTS ix_insurance_policies_h3  ON insurance_policies(h3_cell);

-- A policy's physical risk = PROJECTION of canonical_scores by H3 (insurance's
-- analogue of v_bank_asset_physical_risk / v_sc_plot_physical_risk). A policy
-- whose cell is unscored simply doesn't appear here -- the API surfaces it as
-- 'no_canonical_score' (premium withheld), never a silent zero.
CREATE OR REPLACE VIEW v_insurance_policy_physical_risk AS
SELECT DISTINCT ON (p.policy_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       p.org_id, p.policy_id, p.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   insurance_policies p
JOIN   canonical_scores   cs ON cs.h3_cell = p.h3_cell AND cs.valid_to IS NULL
ORDER  BY p.policy_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;
"""

DOWNGRADE = """
DROP VIEW IF EXISTS v_insurance_policy_physical_risk;
DROP TABLE IF EXISTS insurance_policies;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
