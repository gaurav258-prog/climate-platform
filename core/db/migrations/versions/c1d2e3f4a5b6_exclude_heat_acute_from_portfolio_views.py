"""exclude heat_acute from portfolio physical-risk views

`heat_acute` (today's live ERA5 reading vs climatology, scripts/score_heat_on_demand.py)
is meant for the public single-address /lookup feature, where showing today's
conditions is the point. It was also getting dispatched for every newly-uploaded
portfolio cell (services/scoring/on_demand.py's process_new_cells -> HAZARD_TASKS),
landing in canonical_scores as just another hazard_type row for that cell.

Bank/real-estate/asset-management/supply-chain all pick a "headline" hazard by
taking the MAX score across every hazard_type row for a cell -- so heat_acute
competed directly with heat_chronic (the stable 30-year climatological figure)
to drive valuation haircuts, COGS-at-risk and climate VaR. Net effect: a standing
portfolio number could be set by whatever the ERA5 temperature happened to be on
the day that cell was first scored, not by the location's actual long-run risk --
two identical assets uploaded a week apart could get materially different figures
for no real reason.

Fix: exclude heat_acute at the view level for the four verticals where it has no
legitimate live use (heat_chronic already covers heat for a standing score).
Insurance's view is deliberately left untouched -- heat_acute is real-time by
design for parametric triggers there; its Python headline/pricing computation is
patched separately (api/routers/insurance.py) to skip heat_acute without losing
trigger access to it.

Revision ID: c1d2e3f4a5b6
Revises: a4b5c6d7e8f9
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE OR REPLACE VIEW v_bank_asset_physical_risk AS
SELECT DISTINCT ON (ba.asset_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       ba.org_id,
       ba.asset_id,
       ba.h3_cell,
       cs.hazard_type,
       cs.scenario,
       cs.time_horizon,
       CAST(cs.risk_score AS NUMERIC(5,2)) AS physical_risk_score,
       cs.risk_bucket,
       cs.model_version,
       cs.scored_at,
       'canonical_scores'::text            AS risk_source
FROM   bank_assets      ba
JOIN   canonical_scores cs ON cs.h3_cell = ba.h3_cell
WHERE  cs.valid_to IS NULL AND cs.hazard_type != 'heat_acute'
ORDER  BY ba.asset_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;

CREATE OR REPLACE VIEW v_realestate_property_physical_risk AS
SELECT DISTINCT ON (p.property_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       p.org_id, p.property_id, p.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   realestate_properties p
JOIN   canonical_scores      cs ON cs.h3_cell = p.h3_cell AND cs.valid_to IS NULL
WHERE  cs.hazard_type != 'heat_acute'
ORDER  BY p.property_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;

CREATE OR REPLACE VIEW v_assetmgmt_holding_physical_risk AS
SELECT DISTINCT ON (h.holding_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       h.org_id, h.holding_id, h.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   assetmgmt_holdings h
JOIN   canonical_scores   cs ON cs.h3_cell = h.h3_cell AND cs.valid_to IS NULL
WHERE  cs.hazard_type != 'heat_acute'
ORDER  BY h.holding_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;

CREATE OR REPLACE VIEW v_sc_plot_physical_risk AS
SELECT p.org_id, p.plot_id, p.supplier_id, p.commodity_id, p.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   sc_sourcing_plots p
JOIN   canonical_scores  cs ON cs.h3_cell = p.h3_cell AND cs.valid_to IS NULL
WHERE  cs.hazard_type != 'heat_acute';
"""

DOWNGRADE = """
CREATE OR REPLACE VIEW v_bank_asset_physical_risk AS
SELECT DISTINCT ON (ba.asset_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       ba.org_id,
       ba.asset_id,
       ba.h3_cell,
       cs.hazard_type,
       cs.scenario,
       cs.time_horizon,
       CAST(cs.risk_score AS NUMERIC(5,2)) AS physical_risk_score,
       cs.risk_bucket,
       cs.model_version,
       cs.scored_at,
       'canonical_scores'::text            AS risk_source
FROM   bank_assets      ba
JOIN   canonical_scores cs ON cs.h3_cell = ba.h3_cell
WHERE  cs.valid_to IS NULL
ORDER  BY ba.asset_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;

CREATE OR REPLACE VIEW v_realestate_property_physical_risk AS
SELECT DISTINCT ON (p.property_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       p.org_id, p.property_id, p.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   realestate_properties p
JOIN   canonical_scores      cs ON cs.h3_cell = p.h3_cell AND cs.valid_to IS NULL
ORDER  BY p.property_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;

CREATE OR REPLACE VIEW v_assetmgmt_holding_physical_risk AS
SELECT DISTINCT ON (h.holding_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       h.org_id, h.holding_id, h.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   assetmgmt_holdings h
JOIN   canonical_scores   cs ON cs.h3_cell = h.h3_cell AND cs.valid_to IS NULL
ORDER  BY h.holding_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;

CREATE OR REPLACE VIEW v_sc_plot_physical_risk AS
SELECT p.org_id, p.plot_id, p.supplier_id, p.commodity_id, p.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   sc_sourcing_plots p
JOIN   canonical_scores  cs ON cs.h3_cell = p.h3_cell AND cs.valid_to IS NULL;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
