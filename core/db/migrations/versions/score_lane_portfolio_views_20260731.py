"""Add the standing-lane filter to the 4 physical-risk views that were missing it (audit F1).

The score-lane invariant — "a live nowcast must never drive a published headline; only the calibrated
standing climatology does" — was enforced by adding `cs.score_lane='standing'` to the per-vertical views
in score_lane_20260715. But four views created earlier or later never got it:
  - v_portfolio_entity_physical_risk   (the UNIFIED view all four financial verticals actually read)
  - v_issuer_facility_physical_risk     (SFDR / fund look-through)
  - v_insurance_policy_physical_risk
  - v_assetmgmt_holding_physical_risk
Each joins canonical_scores with only `valid_to IS NULL` and picks `ORDER BY scored_at DESC`, so the
moment a live nowcast row co-exists with the standing row for the same cell/hazard, the nowcast (scored
today) wins and a bank haircut / climate-VaR becomes a function of ingestion timing. (Latent today: the
golden source is currently 100% standing-lane, but the on-demand upload path writes nowcast rows.)

This re-creates the four views verbatim with `AND cs.score_lane = 'standing'` added to the join — no
column change, so CREATE OR REPLACE is safe.

Revision ID: score_lane_portfolio_views_20260731
Revises: ranged_gate_oos_20260731
"""
from alembic import op

revision = "f1_lane_views_20260731"
down_revision = "ranged_gate_oos_20260731"
branch_labels = None
depends_on = None

_LANE = "AND cs.score_lane = 'standing'"


def _views(lane: str) -> list[str]:
    return [
        f"""
        CREATE OR REPLACE VIEW v_portfolio_entity_physical_risk AS
        SELECT DISTINCT ON (e.entity_id, cs.hazard_type, cs.scenario, cs.time_horizon)
               e.org_id, e.entity_id, e.vertical, e.h3_cell,
               cs.hazard_type, cs.risk_score::double precision AS physical_risk_score,
               cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
        FROM portfolio_entities e
        JOIN canonical_scores cs ON cs.h3_cell::text = e.h3_cell::text AND cs.valid_to IS NULL {lane}
        ORDER BY e.entity_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC
        """,
        f"""
        CREATE OR REPLACE VIEW v_issuer_facility_physical_risk AS
        SELECT DISTINCT ON (f.facility_id, cs.hazard_type, cs.scenario, cs.time_horizon)
               f.facility_id, f.issuer_id, f.h3_cell,
               f.materiality_weight::double precision AS materiality_weight,
               cs.hazard_type, cs.risk_score::double precision AS physical_risk_score,
               cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
        FROM issuer_facilities f
        JOIN canonical_scores cs ON cs.h3_cell::text = f.h3_cell::text AND cs.valid_to IS NULL {lane}
        ORDER BY f.facility_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC
        """,
        f"""
        CREATE OR REPLACE VIEW v_insurance_policy_physical_risk AS
        SELECT DISTINCT ON (p.policy_id, cs.hazard_type, cs.scenario, cs.time_horizon)
               p.org_id, p.policy_id, p.h3_cell,
               cs.hazard_type, cs.risk_score::double precision AS physical_risk_score,
               cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
        FROM insurance_policies p
        JOIN canonical_scores cs ON cs.h3_cell::text = p.h3_cell::text AND cs.valid_to IS NULL {lane}
        ORDER BY p.policy_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC
        """,
        f"""
        CREATE OR REPLACE VIEW v_assetmgmt_holding_physical_risk AS
        SELECT DISTINCT ON (h.holding_id, cs.hazard_type, cs.scenario, cs.time_horizon)
               h.org_id, h.holding_id, h.h3_cell,
               cs.hazard_type, cs.risk_score::double precision AS physical_risk_score,
               cs.risk_bucket, cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
        FROM assetmgmt_holdings h
        JOIN canonical_scores cs ON cs.h3_cell::text = h.h3_cell::text AND cs.valid_to IS NULL {lane}
        WHERE cs.hazard_type::text <> 'heat_acute'::text
        ORDER BY h.holding_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC
        """,
    ]


def upgrade():
    for sql in _views(_LANE):
        op.execute(sql)


def downgrade():
    for sql in _views(""):
        op.execute(sql)
