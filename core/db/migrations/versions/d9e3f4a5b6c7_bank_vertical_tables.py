"""bank_vertical_tables

Reconciliation step #3: one DDL source of truth.

The bank-vertical tables previously existed only in a hand-written file
(DATABASE_SCHEMA_REGULATORY_V2.sql) and in the ORM, but in NO migration — so
`alembic upgrade head` did not build them, and the .sql and ORM had drifted
(the .sql carried three dead tables no Python code uses). This migration makes
Alembic build the bank schema from the ORM, ending the split.

Tables are created via metadata.create_all from the ORM definitions (not
hand-copied DDL, so they can't drift from the models). The two views and the
two seed inserts that depend on live tables are ported from the .sql file. The
.sql-only tables (compliance_status, compliance_requirements,
materiality_assessments) and the view that needs them are intentionally NOT
carried over — no code references them; they remain in the deprecated .sql for
reference if ever revived.

Revision ID: d9e3f4a5b6c7
Revises: b7c1a2d3e4f5
Create Date: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op

from core.db.models import Base
import core.db.models_regulatory_complete  # noqa: F401  (registers bank tables)

revision: str = "d9e3f4a5b6c7"
# Bank tables must exist BEFORE c8d2's v_bank_asset_physical_risk view (which
# joins bank_assets ⋈ canonical_scores) and its comment on
# climate_hazard_exposure — so this migration is inserted ahead of c8d2.
down_revision: Union[str, None] = "b7c1a2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The 22 bank-vertical tables (everything in models_regulatory_complete that is
# not a platform table). Explicit list = auditable; create_all orders by FK deps.
BANK_TABLES = [
    "organizations", "users", "bank_assets", "climate_hazard_exposure",
    "climate_risk_scores", "climate_scenarios", "scenario_financial_impact",
    "ghg_emissions_inventory", "governance_structure", "kpi_summary",
    "regulatory_frameworks", "regulation_versions",
    "org_regulation_version_preference", "regulatory_changes",
    "regulatory_change_details", "regulatory_filings", "filing_amendments",
    "regulatory_alerts", "dashboard_notifications", "org_crcs_subscription",
    "org_module_subscriptions", "regulatory_audit_log",
]

VIEWS = [
    # v_org_compliance_status is intentionally omitted — it depends on the
    # dead compliance_status table, not carried over.
    """
    CREATE OR REPLACE VIEW v_asset_climate_risk_summary AS
    SELECT org_id,
           SUM(CASE WHEN risk_category = 'Critical' THEN 1 ELSE 0 END) AS critical_risk_assets,
           SUM(CASE WHEN risk_category = 'High'     THEN 1 ELSE 0 END) AS high_risk_assets,
           AVG(overall_risk_score) AS avg_portfolio_risk_score,
           MAX(overall_risk_score) AS max_portfolio_risk_score,
           assessment_date
    FROM   climate_risk_scores
    GROUP  BY org_id, assessment_date;
    """,
    """
    CREATE OR REPLACE VIEW v_scenario_financial_summary AS
    SELECT org_id, scenario_id, time_horizon,
           COUNT(*) AS assets_assessed,
           AVG(npv_change_from_base_pct) AS avg_npv_change_pct,
           SUM(revenue_impact_eur) AS total_revenue_impact_eur,
           SUM(CASE WHEN is_material THEN 1 ELSE 0 END) AS material_impact_count
    FROM   scenario_financial_impact
    GROUP  BY org_id, scenario_id, time_horizon;
    """,
]

SEED = [
    # PKs supplied via gen_random_uuid(): the ORM UUID PKs use a Python-side
    # default (default=uuid.uuid4), which does not apply to raw SQL inserts, so
    # the seed must generate the id itself.
    """
    INSERT INTO climate_scenarios
      (scenario_id, scenario_name, pathway, temperature_increase_celsius,
       carbon_price_eur_per_ton_2030, carbon_price_eur_per_ton_2050,
       renewable_energy_cost_decline_pct_2030, baseline_year, short_term_year,
       medium_term_year, long_term_year, scenario_source)
    VALUES
      (gen_random_uuid(), 'Paris Agreement (1.5°C)', '1.5c', 1.5, 150, 200, 45, 2024, 2030, 2040, 2050, 'IPCC SSP1-2.6'),
      (gen_random_uuid(), 'Moderate Pathway (2°C)',  '2c',  2.0,  80, 120, 35, 2024, 2030, 2040, 2050, 'IPCC SSP2-4.5'),
      (gen_random_uuid(), 'Business-As-Usual (4°C)', '4c',  4.0,  20,  50, 15, 2024, 2030, 2040, 2050, 'IPCC SSP5-8.5')
    ON CONFLICT DO NOTHING;
    """,
    """
    INSERT INTO regulatory_frameworks
      (framework_id, framework_name, framework_region, mandatory_effective_date,
       enforcing_body, reporting_format, reporting_frequency)
    VALUES
      (gen_random_uuid(), 'TCFD', 'Global', '2025-01-01', 'National regulators', 'Narrative + Quantitative', 'Annual'),
      (gen_random_uuid(), 'EU Taxonomy', 'EU', '2024-01-01', 'European Commission', 'XBRL/iXBRL', 'Annual'),
      (gen_random_uuid(), 'SEC Climate Disclosure', 'US', '2026-01-01', 'SEC', 'Form 10-K', 'Annual'),
      (gen_random_uuid(), 'Basel III Climate', 'Global', '2027-01-01', 'Basel Committee', 'Stress Test', 'Annual'),
      (gen_random_uuid(), 'EBA/ECB Guidelines', 'EU', '2026-01-11', 'ECB', 'Regulatory Report', 'Annual'),
      (gen_random_uuid(), 'UK FCA Climate', 'UK', '2024-06-30', 'FCA', 'Climate Disclosure', 'Annual')
    ON CONFLICT DO NOTHING;
    """,
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in BANK_TABLES]
    Base.metadata.create_all(bind=bind, tables=tables)  # ORM-sourced, FK-ordered
    for view_sql in VIEWS:
        op.execute(view_sql)
    for seed_sql in SEED:
        op.execute(seed_sql)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_scenario_financial_summary")
    op.execute("DROP VIEW IF EXISTS v_asset_climate_risk_summary")
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in BANK_TABLES]
    Base.metadata.drop_all(bind=bind, tables=tables)
