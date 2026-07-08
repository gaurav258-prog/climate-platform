"""Unified portfolio_entities foundation -- one schema for banking, insurance,
real estate and asset management instead of 4 hand-duplicated table sets.

Root problem this fixes: bank_assets/insurance_policies/realestate_properties/
assetmgmt_holdings are 90% identical (name, location, h3_cell, a headline
value, an optional override row, a v_*_physical_risk view) with only a
handful of genuinely vertical-specific fields each. That duplication is why
the heat_acute contamination bug existed in all 4 places, and why every
calc-settings trigger, the deductible fix and the override endpoints each had
to be written 4 times this session instead of once.

New shape:
- portfolio_entities: the shared columns every vertical needs.
- ext_banking / ext_insurance / ext_realestate: thin 1:1 extension tables for
  the fields unique to that vertical (asset management needed none -- its
  fields all fit the shared table).
- portfolio_entity_valuations: ONE override table (was 3).
- v_portfolio_entity_physical_risk: ONE physical-risk view (was 4). Deliberately
  does NOT filter heat_acute here (unlike the old bank/realestate/assetmgmt
  views) -- that exclusion belongs in the engine's headline-selection step
  (services/portfolio_engine.py), same as insurance's existing pattern, so
  insurance's parametric triggers can still see heat_acute while banking/
  real-estate/asset-mgmt's headline/valuation calc excludes it.

Existing primary keys (asset_id/policy_id/property_id/holding_id) are reused
AS-IS as entity_id, so every foreign key that already points at them
(insurance_policy_triggers, the 3 valuation tables, access_audit_log's
target_id text references) keeps working without remapping.

Agriculture (sc_sourcing_plots) deliberately does NOT move here -- a sourcing
plot is a node in a bill-of-materials graph (plot -> supplier -> commodity ->
product -> COGS), not a single-valued entity the same way; forcing it into
this shape would be the wrong kind of uniformity.

Old tables (bank_assets, insurance_policies, realestate_properties,
assetmgmt_holdings, the 3 old valuation tables, the 4 dead Phase-0 tables,
and the 4 old physical-risk views) are NOT dropped in this migration --
they're retired only after the engine + all 4 routers are migrated and
verified against real data (see the follow-up cutover migration).

Revision ID: b9c0d1e2f3a4
Revises: f7a8b9c0d1e2
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE portfolio_entities (
    entity_id           UUID PRIMARY KEY,
    org_id              UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    vertical            VARCHAR(20) NOT NULL CHECK (vertical IN ('banking', 'insurance', 'realestate', 'assetmgmt')),
    entity_name         VARCHAR(200) NOT NULL,
    entity_type         VARCHAR(60),
    sector              VARCHAR(100),
    nace_code           VARCHAR(10),
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    h3_cell             VARCHAR(20),
    country             VARCHAR(2),
    region              VARCHAR(100),
    primary_value_eur   NUMERIC(18,2) NOT NULL,
    construction_type   VARCHAR(40),
    year_built          INTEGER,
    number_of_stories   INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_portfolio_entities_org ON portfolio_entities(org_id);
CREATE INDEX ix_portfolio_entities_h3 ON portfolio_entities(h3_cell);
CREATE INDEX ix_portfolio_entities_vertical ON portfolio_entities(vertical);

CREATE TABLE ext_banking (
    entity_id                      UUID PRIMARY KEY REFERENCES portfolio_entities(entity_id) ON DELETE CASCADE,
    annual_revenue_eur             NUMERIC(18,2),
    expected_lifespan_years        INTEGER,
    gics_code                      VARCHAR(20),
    taxonomy_status                VARCHAR(30),
    taxonomy_activity              VARCHAR(200),
    dnsh_assessment                JSONB,
    energy_consumption_mwh         NUMERIC(18,2),
    ghg_emissions_scope1_tco2e     NUMERIC(18,2),
    ghg_emissions_scope2_tco2e     NUMERIC(18,2),
    ghg_emissions_scope3_tco2e     NUMERIC(18,2),
    carbon_intensity_tco2e_per_meur NUMERIC(18,2),
    insurance_coverage_eur         NUMERIC(18,2),
    insurance_coverage_pct         NUMERIC(5,2),
    resilience_rating              VARCHAR(20),
    data_source                    VARCHAR(100),
    outstanding_loan_balance_eur   NUMERIC(18,2),
    loan_origination_date          DATE
);

CREATE TABLE ext_insurance (
    entity_id                          UUID PRIMARY KEY REFERENCES portfolio_entities(entity_id) ON DELETE CASCADE,
    deductible_pct                     NUMERIC(5,4) NOT NULL DEFAULT 0.02,
    building_value_eur                 NUMERIC(18,2),
    contents_value_eur                 NUMERIC(18,2),
    business_interruption_value_eur    NUMERIC(18,2)
);

CREATE TABLE ext_realestate (
    entity_id           UUID PRIMARY KEY REFERENCES portfolio_entities(entity_id) ON DELETE CASCADE,
    annual_noi_eur      NUMERIC(18,2) NOT NULL
);

CREATE TABLE portfolio_entity_valuations (
    entity_id               UUID PRIMARY KEY REFERENCES portfolio_entities(entity_id) ON DELETE CASCADE,
    override_discount_pct   NUMERIC(5,2) NOT NULL,
    overridden_by           UUID REFERENCES users(user_id),
    overridden_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason                  TEXT
);

CREATE VIEW v_portfolio_entity_physical_risk AS
SELECT DISTINCT ON (e.entity_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       e.org_id, e.entity_id, e.vertical, e.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   portfolio_entities e
JOIN   canonical_scores   cs ON cs.h3_cell = e.h3_cell AND cs.valid_to IS NULL
ORDER  BY e.entity_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;

-- data migration: reuse existing PKs as entity_id so every FK stays valid
INSERT INTO portfolio_entities
    (entity_id, org_id, vertical, entity_name, entity_type, sector, nace_code,
     latitude, longitude, h3_cell, country, region, primary_value_eur,
     construction_type, year_built, number_of_stories, created_at, updated_at)
SELECT asset_id, org_id, 'banking', asset_name, asset_type, sector, nace_code,
       CAST(latitude AS DOUBLE PRECISION), CAST(longitude AS DOUBLE PRECISION), h3_cell, country, region,
       asset_value_eur, NULL, construction_year, NULL,
       COALESCE(created_at, now()), COALESCE(updated_at, now())
FROM bank_assets;

INSERT INTO ext_banking
    (entity_id, annual_revenue_eur, expected_lifespan_years, gics_code, taxonomy_status,
     taxonomy_activity, dnsh_assessment, energy_consumption_mwh,
     ghg_emissions_scope1_tco2e, ghg_emissions_scope2_tco2e, ghg_emissions_scope3_tco2e,
     carbon_intensity_tco2e_per_meur, insurance_coverage_eur, insurance_coverage_pct,
     resilience_rating, data_source, outstanding_loan_balance_eur, loan_origination_date)
SELECT asset_id, annual_revenue_eur, expected_lifespan_years, gics_code, taxonomy_status,
       taxonomy_activity, dnsh_assessment, energy_consumption_mwh,
       ghg_emissions_scope1_tco2e, ghg_emissions_scope2_tco2e, ghg_emissions_scope3_tco2e,
       carbon_intensity_tco2e_per_meur, insurance_coverage_eur, insurance_coverage_pct,
       resilience_rating, data_source, outstanding_loan_balance_eur, loan_origination_date
FROM bank_assets;

INSERT INTO portfolio_entities
    (entity_id, org_id, vertical, entity_name, entity_type, sector, nace_code,
     latitude, longitude, h3_cell, country, region, primary_value_eur,
     construction_type, year_built, number_of_stories, created_at, updated_at)
SELECT policy_id, org_id, 'insurance', policy_name, policy_type, NULL, NULL,
       latitude, longitude, h3_cell, country, region,
       sum_insured_eur, construction_type, year_built, number_of_stories,
       COALESCE(created_at, now()), COALESCE(created_at, now())
FROM insurance_policies;

INSERT INTO ext_insurance (entity_id, deductible_pct, building_value_eur, contents_value_eur, business_interruption_value_eur)
SELECT policy_id, deductible_pct, building_value_eur, contents_value_eur, business_interruption_value_eur
FROM insurance_policies;

INSERT INTO portfolio_entities
    (entity_id, org_id, vertical, entity_name, entity_type, sector, nace_code,
     latitude, longitude, h3_cell, country, region, primary_value_eur,
     construction_type, year_built, number_of_stories, created_at, updated_at)
SELECT property_id, org_id, 'realestate', property_name, property_type, NULL, NULL,
       latitude, longitude, h3_cell, country, region,
       property_value_eur, construction_type, year_built, number_of_stories,
       COALESCE(created_at, now()), COALESCE(created_at, now())
FROM realestate_properties;

INSERT INTO ext_realestate (entity_id, annual_noi_eur)
SELECT property_id, annual_noi_eur FROM realestate_properties;

INSERT INTO portfolio_entities
    (entity_id, org_id, vertical, entity_name, entity_type, sector, nace_code,
     latitude, longitude, h3_cell, country, region, primary_value_eur,
     construction_type, year_built, number_of_stories, created_at, updated_at)
SELECT holding_id, org_id, 'assetmgmt', holding_name, NULL, sector, nace_code,
       latitude, longitude, h3_cell, country, region,
       position_value_eur, NULL, NULL, NULL,
       COALESCE(created_at, now()), COALESCE(created_at, now())
FROM assetmgmt_holdings;

-- valuation overrides: reuse the same entity_id
INSERT INTO portfolio_entity_valuations (entity_id, override_discount_pct, overridden_by, overridden_at, reason)
SELECT asset_id, override_discount_pct, overridden_by, overridden_at, reason FROM bank_asset_valuations
WHERE override_discount_pct IS NOT NULL;

INSERT INTO portfolio_entity_valuations (entity_id, override_discount_pct, overridden_by, overridden_at, reason)
SELECT property_id, override_discount_pct, overridden_by, overridden_at, reason FROM realestate_property_valuations;

INSERT INTO portfolio_entity_valuations (entity_id, override_discount_pct, overridden_by, overridden_at, reason)
SELECT holding_id, override_discount_pct, overridden_by, overridden_at, reason FROM assetmgmt_holding_valuations;

-- repoint insurance_policy_triggers at the unified table (same UUIDs, new FK target)
ALTER TABLE insurance_policy_triggers DROP CONSTRAINT IF EXISTS insurance_policy_triggers_policy_id_fkey;
ALTER TABLE insurance_policy_triggers
    ADD CONSTRAINT insurance_policy_triggers_entity_id_fkey
    FOREIGN KEY (policy_id) REFERENCES portfolio_entities(entity_id) ON DELETE CASCADE;
"""

DOWNGRADE = """
ALTER TABLE insurance_policy_triggers DROP CONSTRAINT IF EXISTS insurance_policy_triggers_entity_id_fkey;
ALTER TABLE insurance_policy_triggers
    ADD CONSTRAINT insurance_policy_triggers_policy_id_fkey
    FOREIGN KEY (policy_id) REFERENCES insurance_policies(policy_id) ON DELETE CASCADE;
DROP VIEW IF EXISTS v_portfolio_entity_physical_risk;
DROP TABLE IF EXISTS portfolio_entity_valuations;
DROP TABLE IF EXISTS ext_realestate;
DROP TABLE IF EXISTS ext_insurance;
DROP TABLE IF EXISTS ext_banking;
DROP TABLE IF EXISTS portfolio_entities;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
