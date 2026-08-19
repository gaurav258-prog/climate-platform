"""realestate_portfolio

Real estate is the platform's 4th vertical, "next build" per the strategy
pass done before this migration: a property schedule, nearly the same shape
as insurance_policies (Statement of Values), projected onto canonical_scores
via the identical view pattern used by bank_assets/v_bank_asset_physical_risk,
sc_sourcing_plots/v_sc_plot_physical_risk, and insurance_policies/
v_insurance_policy_physical_risk -- four verticals, one golden source, four
different projections.

annual_noi_eur is NOT NULL (unlike banking's optional outstanding_loan_balance)
because NOI-impact IS the headline output this vertical exists to produce --
a property with no NOI baseline can't produce the one number the build is for.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE IF NOT EXISTS realestate_properties (
    property_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    property_name     VARCHAR(160) NOT NULL,
    property_type     VARCHAR(40) NOT NULL DEFAULT 'office',
    latitude          DOUBLE PRECISION,
    longitude         DOUBLE PRECISION,
    h3_cell           VARCHAR(20),
    country           VARCHAR(2),
    region            VARCHAR(80),
    property_value_eur NUMERIC(16,2) NOT NULL,
    annual_noi_eur     NUMERIC(16,2) NOT NULL,
    construction_type  VARCHAR(30),
    year_built         INTEGER,
    number_of_stories  INTEGER,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_realestate_properties_org ON realestate_properties(org_id);
CREATE INDEX IF NOT EXISTS ix_realestate_properties_h3  ON realestate_properties(h3_cell);

CREATE OR REPLACE VIEW v_realestate_property_physical_risk AS
SELECT DISTINCT ON (p.property_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       p.org_id, p.property_id, p.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   realestate_properties p
JOIN   canonical_scores      cs ON cs.h3_cell = p.h3_cell AND cs.valid_to IS NULL
ORDER  BY p.property_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;
"""

DOWNGRADE = """
DROP VIEW IF EXISTS v_realestate_property_physical_risk;
DROP TABLE IF EXISTS realestate_properties;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
