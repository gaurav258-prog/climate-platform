"""WS4c — surface the CMIP6 projection band (score_ci) on the financial per-asset views.

The financial hazards (flood/storm/wildfire) now carry a real CMIP6 model-disagreement band on
their forward projections (scripts/project_scenarios.py v2 + the global delta field). These views
dropped the ci columns, so nothing downstream could see the band. Re-create each with
physical_risk_ci_lower/upper appended. Purely additive: same rows, two more (often-NULL) columns.

Revision ID: fin_proj_ci_202608
Revises: sc_crop_calendar_202608
"""
from alembic import op

revision = "fin_proj_ci_202608"
down_revision = "sc_crop_calendar_202608"
branch_labels = None
depends_on = None

_CI_COLS = (",\n           cs.score_ci_lower::double precision AS physical_risk_ci_lower"
            ",\n           cs.score_ci_upper::double precision AS physical_risk_ci_upper")

# (view, entity_id_col, source_table, alias, extra_join_pred, where_pred)
_VIEWS = [
    ("v_portfolio_entity_physical_risk",
     "e.org_id, e.entity_id, e.vertical, e.h3_cell", "portfolio_entities", "e", "entity_id",
     "AND cs.score_lane::text = 'standing'::text", ""),
    ("v_bank_asset_physical_risk",
     "ba.org_id, ba.asset_id, ba.h3_cell", "bank_assets", "ba", "asset_id",
     "", "WHERE cs.valid_to IS NULL AND cs.score_lane::text = 'standing'::text AND cs.hazard_type::text <> 'heat_acute'::text"),
    ("v_realestate_property_physical_risk",
     "p.org_id, p.property_id, p.h3_cell", "realestate_properties", "p", "property_id",
     "", "WHERE cs.score_lane::text = 'standing'::text AND cs.hazard_type::text <> 'heat_acute'::text"),
    ("v_assetmgmt_holding_physical_risk",
     "h.org_id, h.holding_id, h.h3_cell", "assetmgmt_holdings", "h", "holding_id",
     "AND cs.score_lane::text = 'standing'::text", "WHERE cs.hazard_type::text <> 'heat_acute'::text"),
    ("v_insurance_policy_physical_risk",
     "p.org_id, p.policy_id, p.h3_cell", "insurance_policies", "p", "policy_id",
     "AND cs.score_lane::text = 'standing'::text", ""),
]


def _mk(cols, table, alias, key, extra_join, where, with_ci, bank_source=False):
    ci = _CI_COLS if with_ci else ""
    src = ",\n           'canonical_scores'::text AS risk_source" if bank_source else ""
    join_valid = "" if (extra_join or where) else "AND cs.valid_to IS NULL"
    # bank/realestate put valid_to in the JOIN or WHERE explicitly; keep the standing/valid_to on JOIN
    join = (f"JOIN canonical_scores cs ON cs.h3_cell::text = {alias}.h3_cell::text "
            f"AND cs.valid_to IS NULL {extra_join}")
    return f"""
    CREATE VIEW {{name}} AS
    SELECT DISTINCT ON ({alias}.{key}, cs.hazard_type, cs.scenario, cs.time_horizon)
           {cols},
           cs.hazard_type,
           cs.risk_score::double precision AS physical_risk_score,
           cs.risk_bucket,
           cs.scenario,
           cs.time_horizon,
           cs.model_version,
           cs.scored_at{src}{ci}
    FROM {table} {alias}
    {join}
    {where}
    ORDER BY {alias}.{key}, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;
    """


def _apply(with_ci: bool):
    for name, cols, table, alias, key, extra_join, where in _VIEWS:
        bank_source = name == "v_bank_asset_physical_risk"
        op.execute(f"DROP VIEW IF EXISTS {name};")
        op.execute(_mk(cols, table, alias, key, extra_join, where, with_ci, bank_source).format(name=name))


def upgrade() -> None:
    _apply(with_ci=True)


def downgrade() -> None:
    _apply(with_ci=False)
