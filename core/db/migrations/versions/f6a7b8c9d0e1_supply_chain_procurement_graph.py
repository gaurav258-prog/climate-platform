"""supply_chain_procurement_graph

The agriculture / supply-chain vertical: a procurement graph
(product → BOM → commodity → supplier → sourcing plot) whose plots carry an H3
cell, so a plot's physical climate risk is a PROJECTION of canonical_scores —
exactly like bank_assets. This is the data foundation for "COGS-at-risk"
(see docs/SUPPLY_CHAIN_COGS_VAR_SPEC.md). Raw op.execute DDL, self-contained,
mirrors the auth/bank migration style; all org-scoped tables FK organizations.

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
Create Date: 2026-07-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPGRADE = """
-- Commodities catalogue (global; carries the price-response params for the impact fn)
CREATE TABLE IF NOT EXISTS sc_commodities (
    commodity_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(80) NOT NULL UNIQUE,
    hs_code           VARCHAR(12),
    eudr_covered      BOOLEAN NOT NULL DEFAULT false,
    demand_elasticity NUMERIC(6,3),   -- price elasticity of demand (negative; inelastic ~ -0.2)
    global_share_note TEXT,           -- e.g. "Ghana+CIV ~60% of world cocoa"
    primary_hazards   TEXT,           -- e.g. "heat_acute,drought"
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Finished goods (the buyer's SKUs)
CREATE TABLE IF NOT EXISTS sc_products (
    product_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    name               VARCHAR(160) NOT NULL,
    category           VARCHAR(80),
    annual_units       BIGINT,
    annual_revenue_eur NUMERIC(16,2),
    annual_cogs_eur    NUMERIC(16,2),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Suppliers (per commodity)
CREATE TABLE IF NOT EXISTS sc_suppliers (
    supplier_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    name         VARCHAR(160) NOT NULL,
    commodity_id UUID REFERENCES sc_commodities(commodity_id),
    tier         SMALLINT NOT NULL DEFAULT 1,
    country      VARCHAR(2),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bill of materials: SKU → commodity, with the COGS cost-share (the roll-up weight)
CREATE TABLE IF NOT EXISTS sc_bom_lines (
    bom_line_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id       UUID NOT NULL REFERENCES sc_products(product_id) ON DELETE CASCADE,
    commodity_id     UUID NOT NULL REFERENCES sc_commodities(commodity_id),
    cost_share_pct   NUMERIC(5,2) NOT NULL,   -- % of the SKU's COGS from this commodity
    annual_spend_eur NUMERIC(16,2),           -- annual spend on this commodity for this SKU
    UNIQUE (product_id, commodity_id)
);

-- Sourcing plots: supplier × commodity at an H3 cell / GeoJSON (the EUDR geolocation)
CREATE TABLE IF NOT EXISTS sc_sourcing_plots (
    plot_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    supplier_id        UUID REFERENCES sc_suppliers(supplier_id) ON DELETE CASCADE,
    commodity_id       UUID NOT NULL REFERENCES sc_commodities(commodity_id),
    plot_name          VARCHAR(160),
    latitude           DOUBLE PRECISION,
    longitude          DOUBLE PRECISION,
    h3_cell            VARCHAR(20),
    country            VARCHAR(2),
    region             VARCHAR(80),
    annual_spend_eur   NUMERIC(16,2),          -- spend sourced from this plot
    volume_share       NUMERIC(5,4),           -- share of the commodity's volume from this plot
    eudr_status        VARCHAR(20) NOT NULL DEFAULT 'unknown'
                       CHECK (eudr_status IN ('compliant','non_compliant','pending','unknown')),
    eudr_geolocated_at TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_sc_plots_org ON sc_sourcing_plots(org_id);
CREATE INDEX IF NOT EXISTS ix_sc_plots_h3  ON sc_sourcing_plots(h3_cell);
CREATE INDEX IF NOT EXISTS ix_sc_bom_product ON sc_bom_lines(product_id);

-- A plot's physical risk = PROJECTION of canonical_scores by H3 (supply analogue of
-- v_bank_asset_physical_risk). Plots whose cell is unscored simply don't appear here —
-- the API surfaces them as 'no_canonical_score' (€ pending), never a silent zero.
CREATE OR REPLACE VIEW v_sc_plot_physical_risk AS
SELECT p.org_id, p.plot_id, p.supplier_id, p.commodity_id, p.h3_cell,
       cs.hazard_type,
       CAST(cs.risk_score AS FLOAT) AS physical_risk_score,
       cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
FROM   sc_sourcing_plots p
JOIN   canonical_scores  cs ON cs.h3_cell = p.h3_cell AND cs.valid_to IS NULL;
"""

DOWNGRADE = """
DROP VIEW IF EXISTS v_sc_plot_physical_risk;
DROP TABLE IF EXISTS sc_sourcing_plots;
DROP TABLE IF EXISTS sc_bom_lines;
DROP TABLE IF EXISTS sc_suppliers;
DROP TABLE IF EXISTS sc_products;
DROP TABLE IF EXISTS sc_commodities;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
