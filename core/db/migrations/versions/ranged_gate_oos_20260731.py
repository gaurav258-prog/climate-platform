"""Gate the 'ranged' publish tier on OUT-OF-SAMPLE r² (r2_oos), not in-sample r².

WHY (audit finding F2). The publish floor is the platform's central honesty claim: "a euro is a firm
figure only where the driver clears r² ≥ 0.40." But the tier view gated on `f.r2` — the IN-SAMPLE r²,
which the fitting code itself labels "the optimistic number" — while `f.r2_oos` (leave-one-out cross-
validated, "the HONEST predictive number") only fed the advisory Confidence Grade. At the n=12-year
minimum, in-sample and OOS diverge most, so a crop could publish a € band on an optimistic 0.42 whose
honest OOS skill is 0.24. Gating on r2_oos closes that gap. (r2_oos ≤ r2 always, so this is strictly
stricter; NULL r2_oos → not published, the conservative default.)

Effect on the live book: retires exactly 'Durum wheat / ES' (r2_oos 0.237) and 'Wheat / IR' (0.327) from
the published-euro set; the other seven ranged crops clear OOS and are unaffected.

Revision ID: ranged_gate_oos_20260731
Revises: regside_ops_20260730
"""
from alembic import op

revision = "ranged_gate_oos_20260731"
down_revision = "regside_ops_20260730"
branch_labels = None
depends_on = None

_FLOOR = "0.40"   # single publish floor; mirrored by services.intelligence.supply_cogs.RANGED_PUBLISH_FLOOR


def _view(ranged_condition: str) -> str:
    return f"""
        CREATE OR REPLACE VIEW v_sc_commodity_calibration AS
        SELECT c.commodity_id, c.origin, c.sensitivity, c.world_share, c.hazard_driver,
               c.event_ref, c.source_note, c.impact_version, c.region_key, c.season_months,
               c.scoring_model, c.baseline_from, c.baseline_to,
               CASE
                 WHEN EXISTS (SELECT 1 FROM sc_model_validation v
                              WHERE v.commodity_id = c.commodity_id
                                AND v.origin::text = c.origin::text
                                AND v.passed
                                AND v.hazard::text = c.hazard_driver::text)
                   THEN 'backtested'
                 WHEN EXISTS (SELECT 1 FROM sc_commodity_fit f
                              WHERE f.commodity_id = c.commodity_id
                                AND f.origin::text = c.origin::text
                                AND f.hazard_driver::text = c.hazard_driver::text
                                AND {ranged_condition})
                   THEN 'ranged'
                 ELSE 'indicative'
               END AS calibration_tier
        FROM sc_commodity_calibration c
    """


def upgrade():
    op.execute(_view(f"f.r2_oos >= {_FLOOR}"))


def downgrade():
    op.execute(_view(f"f.r2 >= {_FLOOR}"))
