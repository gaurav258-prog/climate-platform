"""'ranged' requires the fit to clear the publish floor (r² >= 0.40); weaker fits are STORED but HELD.

WHY. We want to store a crop's fit even when it is too weak to publish — so the product can say
"we tested drought on your wheat; it explains 36% of bad years, below our 40% bar, so we show the
exposure and withhold the €." That is a stronger trust signal than a bare "not validated". But the
tier view previously made ANY stored fit 'ranged' (publishable). So it must now gate on r²: a fit
at or above the floor is 'ranged'; a weaker fit leaves the crop 'indicative' (held) while remaining
visible on the Trust page and as the held-reason.

0.40 is the same floor scripts/fit_ranged_crop.py enforces (MIN_R2) — kept in lockstep by comment.
The tier stays DERIVED; you still cannot type your way to a published euro.
"""
from alembic import op

revision = "ranged_floor_20260718"
down_revision = "ranged_tier_20260718"
branch_labels = None
depends_on = None

_FLOOR = "0.40"   # must match scripts/fit_ranged_crop.py MIN_R2


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
    op.execute(_view(f"f.r2 >= {_FLOOR}"))


def downgrade():
    op.execute(_view("TRUE"))
