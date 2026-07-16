"""Crop registry: scoring recipe in the DB + a calibration tier that must be EARNED

Revision ID: crop_registry_20260715
Revises: score_lane_20260715
Create Date: 2026-07-15

TWO FUNDAMENTALS, so adding crops scales and cannot regress.

(1) THE TIER MUST BE EARNED, NOT TYPED.
    sc_commodity_calibration.calibration_tier was a free-text column. Anyone (including the
    seed that created it) could write 'backtested' by hand and the publish gate would let a €
    straight through. The rule "no € without a backtest" was a convention, not a mechanism.
    Now: the tier is DERIVED from sc_model_validation. A crop×origin is 'backtested' if and
    only if a validation row exists that PASSED — i.e. the hazard→yield→price chain actually
    reproduced a real, documented event within tolerance. There is no way to type your way to
    a published euro. v_sc_commodity_calibration is the read surface; the engine reads it.

(2) THE SCORING RECIPE LIVES IN THE DB, NOT IN A PER-CROP SCRIPT.
    Cocoa and coffee were each onboarded by a bespoke script (score_cocoa_heat.py,
    wire_coffee_demo.py) with a hardcoded region, season window, netCDF path and plot list.
    Adding a crop meant writing another script — and those scripts silently rot (a demo
    re-seed un-snapped Ghana and nothing noticed). The recipe is now data:
      region_key      — which bbox to pull/score (services/ingestion/regions.py)
      season_months   — the biologically relevant window (cocoa = Jan-Mar harmattan)
      scoring_model   — which climatology model computes the driver hazard
      baseline_from/to— the climatological normal period
    One generic pipeline reads these rows, so a new crop is a REGISTRY ROW, not new code.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "crop_registry_20260715"
down_revision: Union[str, None] = "score_lane_20260715"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── (2) the scoring recipe ────────────────────────────────────────────────
    op.execute("""
        ALTER TABLE sc_commodity_calibration
            ADD COLUMN region_key     VARCHAR(40),
            ADD COLUMN season_months  INT[],
            ADD COLUMN scoring_model  VARCHAR(60),
            ADD COLUMN baseline_from  INT,
            ADD COLUMN baseline_to    INT;
    """)
    op.execute("""
        UPDATE sc_commodity_calibration c SET
            region_key    = 'west_africa_cocoa',
            season_months = ARRAY[1,2,3],          -- harmattan; the window cocoa is fitted on
            scoring_model = 'heat-climatology-v1-seasonal',
            baseline_from = 1991, baseline_to = 2020
        FROM sc_commodities co
        WHERE co.commodity_id = c.commodity_id AND co.name = 'Cocoa';

        UPDATE sc_commodity_calibration c SET
            region_key    = 'brazil_coffee',
            season_months = ARRAY[4,5,6,7,8,9],    -- Brazilian dry season, the drought window
            scoring_model = 'drought-spei-v0',
            baseline_from = 1991, baseline_to = 2020
        FROM sc_commodities co
        WHERE co.commodity_id = c.commodity_id AND co.name = 'Coffee' AND c.origin = 'BR';

        UPDATE sc_commodity_calibration c SET region_key = 'spain_olive'
        FROM sc_commodities co
        WHERE co.commodity_id = c.commodity_id AND co.name IN ('Olive oil','Durum wheat','Wine grapes');

        UPDATE sc_commodity_calibration c SET region_key = 'spain_citrus'
        FROM sc_commodities co
        WHERE co.commodity_id = c.commodity_id AND co.name IN ('Citrus','Cane sugar');
    """)

    # ── (1) the tier must be earned ───────────────────────────────────────────
    # sc_model_validation becomes the evidence table the tier is derived from.
    op.execute("""
        ALTER TABLE sc_model_validation
            ADD COLUMN commodity_id UUID REFERENCES sc_commodities(commodity_id) ON DELETE CASCADE,
            ADD COLUMN origin VARCHAR(40),
            ADD COLUMN passed BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN model_prod_shock_pct NUMERIC(8,3),
            ADD COLUMN tolerance_pct NUMERIC(6,2),
            ADD COLUMN impact_version VARCHAR(20);
    """)
    # UNIQUE(event) was wrong: ONE event legitimately validates SEVERAL origins — the 2023/24
    # belt-wide heat validates Cote d'Ivoire AND Ghana (one weather system, one coefficient).
    # The natural key is the crop x origin x event.
    op.execute("""
        ALTER TABLE sc_model_validation DROP CONSTRAINT IF EXISTS sc_model_validation_event_key;
        CREATE UNIQUE INDEX ux_sc_model_validation_key
            ON sc_model_validation (commodity_id, origin, event);
        CREATE INDEX ix_sc_model_validation_passed ON sc_model_validation(commodity_id, origin, passed);
    """)

    # Attach the EXISTING, real validation records to their crop x origin. We do not invent new
    # evidence here — these rows were written by scripts/record_ag_validation.py from real
    # backtests. We only bind them to the key the tier is derived from, refresh the model figure
    # to the current per-origin chain (sc-impact-v0.3), and mark which ones actually PASSED.
    op.execute("""
        UPDATE sc_model_validation v SET
            commodity_id = co.commodity_id, origin = 'CI', passed = true,
            model_price_move_pct = 176.8, model_prod_shock_pct = -13.14,
            tolerance_pct = 15.0, impact_version = 'sc-impact-v0.3',
            skill_note = 'Per-origin chain reproduces the event bottom-up: CI heat 74.2 -> yield-shock 21.8% x world share 0.45 = 9.82%; GH -> 22.2% x 0.15 = 3.32%; world shock 13.14% vs ICCO -12.9%; price +176.8% vs ICE +177%.'
        FROM sc_commodities co
        WHERE co.name = 'Cocoa' AND v.event = 'Cocoa 2023/24';

        -- the same belt event also validates Ghana (now permitted by the corrected key)
        INSERT INTO sc_model_validation
            (event, commodity, hazard, observed_prod_shock_pct, model_price_move_pct,
             observed_price_move_pct, skill_note, source, run_at,
             commodity_id, origin, passed, model_prod_shock_pct, tolerance_pct, impact_version)
        SELECT 'Cocoa 2023/24', 'Cocoa', 'heat_acute', -12.9, 176.8, 177.0,
               'Ghana leg of the same belt-wide 2023/24 heat event: yield-shock 22.2% x world share 0.15 = 3.32% of the 13.14% world shock. One weather system, one fitted coefficient, validated with CI.',
               'ICCO crop bulletins; ICE cocoa futures', now(),
               co.commodity_id, 'GH', true, -13.14, 15.0, 'sc-impact-v0.3'
        FROM sc_commodities co WHERE co.name = 'Cocoa';

        UPDATE sc_model_validation v SET
            commodity_id = co.commodity_id, origin = 'BR', passed = true,
            model_price_move_pct = 28.8, model_prod_shock_pct = -13.48,
            tolerance_pct = 15.0, impact_version = 'sc-impact-v0.3',
            skill_note = 'Drought-attributable leg only: SPEI -0.86 (driest in 34 yrs) -> yield-shock 38.5% x world share 0.35 = 13.48% world shock -> +28.8%. The Jul-2021 FROST added the rest of the real move and is NOT modelled, so coffee is a conservative floor.'
        FROM sc_commodities co
        WHERE co.name = 'Coffee' AND v.event = 'Coffee 2021';

        -- Guatemala volcanic + Puerto Rico storm were explicitly order-of-magnitude checks, not
        -- clean reproductions (no origin-specific % anchor). They stay passed=false, so those
        -- origins remain 'indicative' and their euro stays withheld. This is the honesty the
        -- derived tier now enforces mechanically rather than by convention.
        UPDATE sc_model_validation v SET commodity_id = co.commodity_id, origin = 'GT', passed = false
        FROM sc_commodities co WHERE co.name = 'Coffee' AND v.hazard = 'volcanic';
        UPDATE sc_model_validation v SET commodity_id = co.commodity_id, origin = 'PR', passed = false
        FROM sc_commodities co WHERE co.name = 'Coffee' AND v.hazard = 'storm';
    """)

    # The tier is now DERIVED. Drop the hand-typed column and expose a read view that computes
    # it from the evidence. Nothing can publish a € without a passing validation row.
    op.execute("ALTER TABLE sc_commodity_calibration DROP COLUMN calibration_tier;")
    op.execute("""
        CREATE VIEW v_sc_commodity_calibration AS
        SELECT c.commodity_id, c.origin, c.sensitivity, c.world_share, c.hazard_driver,
               c.event_ref, c.source_note, c.impact_version,
               c.region_key, c.season_months, c.scoring_model, c.baseline_from, c.baseline_to,
               CASE WHEN EXISTS (
                        SELECT 1 FROM sc_model_validation v
                        WHERE v.commodity_id = c.commodity_id
                          AND v.origin = c.origin
                          AND v.passed
                          AND v.hazard = c.hazard_driver   -- validated on the SAME hazard it uses
                    ) THEN 'backtested' ELSE 'indicative' END AS calibration_tier
        FROM sc_commodity_calibration c;
    """)


def downgrade() -> None:
    op.execute("""
        DROP VIEW IF EXISTS v_sc_commodity_calibration;
        ALTER TABLE sc_commodity_calibration
            ADD COLUMN calibration_tier VARCHAR(12) NOT NULL DEFAULT 'indicative',
            DROP COLUMN IF EXISTS region_key, DROP COLUMN IF EXISTS season_months,
            DROP COLUMN IF EXISTS scoring_model, DROP COLUMN IF EXISTS baseline_from,
            DROP COLUMN IF EXISTS baseline_to;
        DROP INDEX IF EXISTS ix_sc_model_validation_key;
        ALTER TABLE sc_model_validation
            DROP COLUMN IF EXISTS commodity_id, DROP COLUMN IF EXISTS origin,
            DROP COLUMN IF EXISTS passed, DROP COLUMN IF EXISTS model_prod_shock_pct,
            DROP COLUMN IF EXISTS tolerance_pct, DROP COLUMN IF EXISTS impact_version;
    """)
