"""asset_manager_holdings_foundation

Revision ID: f8a9b0c1d2e3
Revises: e6f7a8b9c0d1
Create Date: 2026-07-11

THE foundation for the asset-management product. The existing single-point
`portfolio_entities` model is correct for holders of LOCATED assets (banks'
collateral, insurers' SOV, REITs' buildings, agri plots) and is left untouched.
But an asset manager does not hold located assets — it holds SECURITIES that
reference ISSUERS that own geographically-distributed FOOTPRINTS, aggregated up
a FUND hierarchy. That graph has no home in `portfolio_entities`, so this
migration builds it as a distinct layer, keyed to the SAME golden source.

Graph (leaf → root):
    canonical_scores (h3_cell)          -- existing physical golden source, reused
      └─ issuer_facilities (many per issuer, H3-located, materiality-weighted)
           └─ issuers (LEI identity; corporate / sovereign / securitized / supra)
                └─ securities (ISIN/CUSIP/... → issuer; asset_class; currency)
                     └─ fund_positions (security held in a fund, valued, dated)
                          └─ funds (reporting entity; self-referential hierarchy)
                               └─ organizations (tenant, existing)

Two score surfaces, deliberately separate because they are keyed differently:
  * PHYSICAL risk is a property of a LOCATION -> stays in canonical_scores (h3),
    reached via issuer_facilities.h3_cell. An issuer's physical score is the
    materiality-weighted roll-up of its facilities' scores (computed in the
    engine, Phase 2 -- not faked here).
  * TRANSITION risk is a property of an ISSUER/SECTOR, not a map cell -> its own
    append-only golden surface `issuer_transition_scores` (issuer-keyed),
    mirroring canonical_scores' valid_from/valid_to supersession discipline.
    Raw disclosed emissions land in `issuer_emissions`; the transition MODEL
    (Phase 4) computes scores FROM them -- raw intake and computed score are
    kept separate on purpose (no conflation).

Nothing here computes a score or fabricates data -- this is purely the
relational foundation. Weighted physical roll-up (Phase 2), fund aggregation
(Phase 3), and the transition model (Phase 4) build on top.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
-- ── Issuers: the legal entity a security references ──────────────────────
CREATE TABLE issuers (
    issuer_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lei           VARCHAR(20) UNIQUE,                        -- Legal Entity Identifier, if known
    name          VARCHAR(300) NOT NULL,
    issuer_type   VARCHAR(20) NOT NULL DEFAULT 'corporate'
                  CHECK (issuer_type IN ('corporate','sovereign','securitized','supranational','municipal')),
    country       VARCHAR(2),                                -- domicile / for sovereigns, the country
    sector        VARCHAR(100),
    nace_code     VARCHAR(10),                               -- feeds EU Taxonomy classifier
    gics_sector   VARCHAR(60),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_issuers_country ON issuers(country);
CREATE INDEX ix_issuers_nace ON issuers(nace_code);

-- ── Issuer footprint: the many physical facilities an issuer owns ────────
-- This is the core fix for "one lat/lon per holding". An issuer's physical
-- climate risk is the materiality-weighted aggregate of THESE, each scored via
-- its h3_cell against canonical_scores.
CREATE TABLE issuer_facilities (
    facility_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer_id          UUID NOT NULL REFERENCES issuers(issuer_id) ON DELETE CASCADE,
    name               VARCHAR(200),
    facility_type      VARCHAR(40),                          -- plant / office / mine / hq / warehouse / farm / substation ...
    latitude           DOUBLE PRECISION,
    longitude          DOUBLE PRECISION,
    h3_cell            VARCHAR(20),                          -- join key to canonical_scores
    country            VARCHAR(2),
    region             VARCHAR(100),
    materiality_weight NUMERIC(8,6) NOT NULL DEFAULT 0,      -- share of the issuer's footprint (weights per issuer ~sum to 1)
    weight_basis       VARCHAR(20) NOT NULL DEFAULT 'equal'  -- how the weight was derived (disclosure, not a guess)
                       CHECK (weight_basis IN ('revenue','assets','production_capacity','headcount','equal')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_facilities_issuer ON issuer_facilities(issuer_id);
CREATE INDEX ix_facilities_h3 ON issuer_facilities(h3_cell);

-- ── Securities master: instrument -> issuer ─────────────────────────────
CREATE TABLE securities (
    security_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    isin           VARCHAR(12) UNIQUE,
    cusip          VARCHAR(9),
    sedol          VARCHAR(7),
    ticker         VARCHAR(20),
    name           VARCHAR(300) NOT NULL,
    issuer_id      UUID NOT NULL REFERENCES issuers(issuer_id) ON DELETE CASCADE,
    asset_class    VARCHAR(20) NOT NULL DEFAULT 'equity'
                   CHECK (asset_class IN ('equity','corporate_bond','sovereign_bond','securitized','etf','fund','other')),
    currency       VARCHAR(3),
    is_lookthrough BOOLEAN NOT NULL DEFAULT false,           -- ETFs/funds expand to constituents (a fund_of_funds parent)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (isin IS NOT NULL OR cusip IS NOT NULL OR sedol IS NOT NULL OR ticker IS NOT NULL)
);
CREATE INDEX ix_securities_issuer ON securities(issuer_id);
CREATE INDEX ix_securities_cusip ON securities(cusip);

-- ── Funds: the reporting entity, with a self-referential hierarchy ──────
-- The reporting unit for an asset manager is the FUND, not the firm. A
-- fund-of-funds / mandate-with-sub-portfolios is expressed via parent_fund_id.
CREATE TABLE funds (
    fund_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    name                VARCHAR(200) NOT NULL,
    fund_type           VARCHAR(30) NOT NULL DEFAULT 'fund'
                        CHECK (fund_type IN ('fund','sub_portfolio','mandate','fund_of_funds')),
    parent_fund_id      UUID REFERENCES funds(fund_id) ON DELETE CASCADE,   -- NULL = top-level
    sfdr_classification VARCHAR(12)
                        CHECK (sfdr_classification IN ('article_6','article_8','article_9') OR sfdr_classification IS NULL),
    base_currency       VARCHAR(3) NOT NULL DEFAULT 'EUR',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_funds_org ON funds(org_id);
CREATE INDEX ix_funds_parent ON funds(parent_fund_id);

-- ── Fund positions: a security held in a fund, valued and dated ─────────
CREATE TABLE fund_positions (
    position_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fund_id            UUID NOT NULL REFERENCES funds(fund_id) ON DELETE CASCADE,
    security_id        UUID NOT NULL REFERENCES securities(security_id) ON DELETE CASCADE,
    quantity           NUMERIC(24,6),
    market_value_base  NUMERIC(20,2),                        -- in the fund's base currency
    market_value_eur   NUMERIC(20,2) NOT NULL,               -- normalized, so cross-fund/firm roll-up is currency-correct
    weight_pct         NUMERIC(9,6),                         -- position weight within the fund
    as_of_date         DATE NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (fund_id, security_id, as_of_date)                -- one position per security per fund per snapshot date
);
CREATE INDEX ix_positions_fund ON fund_positions(fund_id, as_of_date);
CREATE INDEX ix_positions_security ON fund_positions(security_id);

-- ── Issuer emissions: raw disclosed/estimated inputs to the transition model ──
-- Kept separate from the computed transition score: this is INPUT data, not a
-- result. The transition model (Phase 4) reads from here.
CREATE TABLE issuer_emissions (
    emission_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer_id       UUID NOT NULL REFERENCES issuers(issuer_id) ON DELETE CASCADE,
    reporting_year  INTEGER NOT NULL,
    scope1_tco2e    NUMERIC(20,2),
    scope2_tco2e    NUMERIC(20,2),
    scope3_tco2e    NUMERIC(20,2),
    revenue_eur     NUMERIC(20,2),                           -- denominator for carbon intensity / WACI
    source          VARCHAR(40) NOT NULL DEFAULT 'disclosed' -- disclosed / estimated / cdp / vendor (provenance, never hidden)
                    CHECK (source IN ('disclosed','estimated','cdp','vendor')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (issuer_id, reporting_year, source)
);
CREATE INDEX ix_emissions_issuer ON issuer_emissions(issuer_id);

-- ── Transition-risk golden surface: issuer-keyed, append-only ───────────
-- The transition analogue of canonical_scores. Same supersession discipline
-- (valid_from/valid_to, nothing overwritten). Populated by the Phase-4 model.
CREATE TABLE issuer_transition_scores (
    transition_score_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer_id                    UUID NOT NULL REFERENCES issuers(issuer_id) ON DELETE CASCADE,
    scenario                     VARCHAR(50) NOT NULL,
    time_horizon                 VARCHAR(20) NOT NULL,
    transition_risk_score        NUMERIC(5,2) NOT NULL CHECK (transition_risk_score BETWEEN 0 AND 100),
    risk_bucket                  VARCHAR(5) NOT NULL,
    carbon_intensity_tco2e_per_meur NUMERIC(18,4),           -- the WACI building block
    stranded_asset_pct           NUMERIC(6,3),               -- fraction of value at risk of stranding
    carbon_price_impact_eur      NUMERIC(20,2),              -- modeled value impact at the scenario's carbon price
    model_version                VARCHAR(50) NOT NULL,
    data_vintage                 TIMESTAMPTZ NOT NULL,
    valid_from                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to                     TIMESTAMPTZ,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_transition_current ON issuer_transition_scores(issuer_id, scenario, time_horizon)
    WHERE valid_to IS NULL;

-- ── Facility physical-risk view: each facility joined to its CURRENT scores ──
-- The reusable join (facility.h3_cell -> canonical_scores). The issuer-level
-- materiality-weighted roll-up is done in the engine, not here, so the
-- headline/heat_acute/severity-model rules live in ONE place (Phase 2).
CREATE VIEW v_issuer_facility_physical_risk AS
SELECT DISTINCT ON (f.facility_id, cs.hazard_type, cs.scenario, cs.time_horizon)
       f.facility_id, f.issuer_id, f.h3_cell,
       CAST(f.materiality_weight AS FLOAT) AS materiality_weight,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   issuer_facilities f
JOIN   canonical_scores  cs ON cs.h3_cell = f.h3_cell AND cs.valid_to IS NULL
ORDER  BY f.facility_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;
"""

DOWNGRADE = """
DROP VIEW IF EXISTS v_issuer_facility_physical_risk;
DROP TABLE IF EXISTS issuer_transition_scores;
DROP TABLE IF EXISTS issuer_emissions;
DROP TABLE IF EXISTS fund_positions;
DROP TABLE IF EXISTS funds;
DROP TABLE IF EXISTS securities;
DROP TABLE IF EXISTS issuer_facilities;
DROP TABLE IF EXISTS issuers;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
