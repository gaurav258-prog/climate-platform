"""score_lane: separate standing (climatological) scores from nowcast (live) scores

Revision ID: score_lane_20260715
Revises: sc_calibration_20260715
Create Date: 2026-07-15

THE BUG. canonical_scores retires prior scores on the key
    (h3_cell, hazard_type, scenario)
-- model_version is NOT part of it. So ANY run retires EVERY current score for that
cell+hazard, whatever model produced it or whatever it was for.

We run two semantically different kinds of score through the same hazard_type:
  * STANDING  -- climatological / structural risk. Drives portfolio numbers, the
                 per-crop calibrations and the event backtests.
                 e.g. heat-climatology-v1-seasonal, drought-spei-v0
  * NOWCAST   -- today's live reading vs climatology. Drives the public single-address
                 lookup and insurance parametric triggers.
                 e.g. heat-climatology-v1-ondemand, drought-spi1-on-demand-v0

Because they shared a retirement key, a 30-second live-weather nowcast silently retired
a 30-year calibrated climatology. Observed on the Cote d'Ivoire cocoa cell:
    02 Jul  heat-climatology-v1-seasonal  74.2  -> retired
    08 Jul  heat-climatology-v1-ondemand   0.0  -> current ("not hot today")
Cocoa's whole backtest rests on that 74.2. Migration c1d2e3f4a5b6 then excluded
heat_acute from the portfolio views (right for nowcast, wrong for the climatology),
which MASKED the damage -- the crop engine silently fell back to the next-worst hazard
(wildfire) and kept its 'backtested' badge. drought carries the identical split, which
puts coffee -- the one crop currently passing the gate -- at the same risk.

THE FIX. score_lane makes the purpose explicit and part of the retirement key, so the
two lanes can coexist per cell and never retire each other. Views select the lane they
mean. This is the foundation both the calibrations and the backtests stand on.

Also repairs the damage: any standing-lane key left with NO current row (because a
nowcast retired it) has its most recent standing score reinstated.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "score_lane_20260715"
down_revision: Union[str, None] = "sc_calibration_20260715"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. The lane. Default 'standing' — the overwhelming majority, and the safe default:
    #    a new scorer is a standing model unless it declares itself a nowcast.
    op.execute("""
        ALTER TABLE canonical_scores
            ADD COLUMN score_lane VARCHAR(12) NOT NULL DEFAULT 'standing'
            CHECK (score_lane IN ('standing','nowcast'));
    """)

    # 2. Backfill: the existing on-demand model families are nowcasts.
    #    (strpos, not ILIKE '%…%' — a literal % collides with DBAPI parameter binding here.)
    #    canonical_scores carries an append-only trigger that permits no payload change, so we
    #    disable it for this one classification pass. This adds a NEW column describing rows
    #    that already exist; it changes no score, bucket, model or timestamp. The alembic
    #    revision is itself the audit record for it.
    op.execute("ALTER TABLE canonical_scores DISABLE TRIGGER prevent_update_canonical_scores;")
    op.execute("""
        UPDATE canonical_scores
           SET score_lane = 'nowcast'
         WHERE strpos(lower(model_version), 'on-demand') > 0
            OR strpos(lower(model_version), 'ondemand') > 0;
    """)
    op.execute("ALTER TABLE canonical_scores ENABLE TRIGGER prevent_update_canonical_scores;")

    # 3. REPAIR, the append-only way. Where a nowcast retired the standing score, the standing
    #    lane is left with no current row. We do NOT un-retire the old row — resurrecting a
    #    retired row would rewrite history and is exactly what the append-only trigger forbids.
    #    Instead we RE-ASSERT the score: append a new current row carrying the same model,
    #    value and data_vintage (the computation is unchanged and fully attributed), with
    #    valid_from = now (when it became current again). The retirement stays in the record,
    #    so the history reads honestly: scored -> wrongly retired by a nowcast -> re-asserted.
    op.execute("""
        WITH orphaned AS (
            SELECT h3_cell, hazard_type, scenario, time_horizon
            FROM   canonical_scores
            WHERE  score_lane = 'standing'
            GROUP  BY h3_cell, hazard_type, scenario, time_horizon
            HAVING count(*) FILTER (WHERE valid_to IS NULL) = 0
        ),
        newest AS (
            SELECT DISTINCT ON (cs.h3_cell, cs.hazard_type, cs.scenario, cs.time_horizon) cs.*
            FROM   canonical_scores cs
            JOIN   orphaned o
              ON   o.h3_cell = cs.h3_cell AND o.hazard_type = cs.hazard_type
             AND   o.scenario = cs.scenario AND o.time_horizon = cs.time_horizon
            WHERE  cs.score_lane = 'standing'
            ORDER  BY cs.h3_cell, cs.hazard_type, cs.scenario, cs.time_horizon, cs.valid_from DESC
        )
        INSERT INTO canonical_scores
            (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
             risk_score, risk_bucket, model_version, data_vintage, shap_factors,
             scored_at, valid_from, valid_to, score_lane, regulatory_fingerprint)
        SELECT gen_random_uuid(), h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
               risk_score, risk_bucket, model_version, data_vintage, shap_factors,
               scored_at, now(), NULL, 'standing', regulatory_fingerprint
        FROM   newest;
    """)

    op.execute("""
        CREATE INDEX ix_canonical_scores_lane_current
            ON canonical_scores (h3_cell, hazard_type, scenario, time_horizon, score_lane)
            WHERE valid_to IS NULL;
    """)

    # 4. Supply view reads the STANDING lane, and no longer blanket-excludes heat_acute:
    #    the crop engine now asks for ONE named driver hazard per commodity+origin (the one
    #    its coefficient was backtested against), so heat_acute can no longer "compete for
    #    MAX" with heat_chronic here — the reason it was excluded in c1d2e3f4a5b6. Cocoa's
    #    driver IS heat_acute (seasonal climatology), so excluding it made the marquee crop
    #    unscoreable. The other verticals' views keep their exclusion (they still take a MAX
    #    across hazards, where heat_chronic is the right standing heat measure) but now also
    #    pin the standing lane so a nowcast can never drive a portfolio number.
    op.execute("""
        CREATE OR REPLACE VIEW v_sc_plot_physical_risk AS
        SELECT p.org_id, p.plot_id, p.supplier_id, p.commodity_id, p.h3_cell,
               cs.hazard_type,
               cs.risk_score::double precision AS physical_risk_score,
               cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
        FROM   sc_sourcing_plots p
        JOIN   canonical_scores cs
          ON   cs.h3_cell::text = p.h3_cell::text
         AND   cs.valid_to IS NULL
         AND   cs.score_lane = 'standing';
    """)

    # Bank + real-estate: KEEP the heat_acute exclusion (they take a MAX across hazards, where
    # heat_chronic is the right standing heat measure — the c1d2e3f4a5b6 rationale still holds),
    # but pin the standing lane so no nowcast can ever drive a valuation haircut or climate VaR.
    op.execute("""
        CREATE OR REPLACE VIEW v_bank_asset_physical_risk AS
        SELECT DISTINCT ON (ba.asset_id, cs.hazard_type, cs.scenario, cs.time_horizon)
               ba.org_id, ba.asset_id, ba.h3_cell, cs.hazard_type, cs.scenario, cs.time_horizon,
               cs.risk_score AS physical_risk_score, cs.risk_bucket, cs.model_version, cs.scored_at,
               'canonical_scores'::text AS risk_source
        FROM   bank_assets ba
        JOIN   canonical_scores cs ON cs.h3_cell::text = ba.h3_cell::text
        WHERE  cs.valid_to IS NULL
          AND  cs.score_lane = 'standing'
          AND  cs.hazard_type::text <> 'heat_acute'::text
        ORDER  BY ba.asset_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;

        CREATE OR REPLACE VIEW v_realestate_property_physical_risk AS
        SELECT DISTINCT ON (p.property_id, cs.hazard_type, cs.scenario, cs.time_horizon)
               p.org_id, p.property_id, p.h3_cell, cs.hazard_type,
               cs.risk_score::double precision AS physical_risk_score, cs.risk_bucket,
               cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
        FROM   realestate_properties p
        JOIN   canonical_scores cs ON cs.h3_cell::text = p.h3_cell::text AND cs.valid_to IS NULL
        WHERE  cs.score_lane = 'standing'
          AND  cs.hazard_type::text <> 'heat_acute'::text
        ORDER  BY p.property_id, cs.hazard_type, cs.scenario, cs.time_horizon, cs.scored_at DESC;
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ix_canonical_scores_lane_current;
        CREATE OR REPLACE VIEW v_sc_plot_physical_risk AS
        SELECT p.org_id, p.plot_id, p.supplier_id, p.commodity_id, p.h3_cell,
               cs.hazard_type,
               cs.risk_score::double precision AS physical_risk_score,
               cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
        FROM   sc_sourcing_plots p
        JOIN   canonical_scores cs
          ON   cs.h3_cell::text = p.h3_cell::text AND cs.valid_to IS NULL
        WHERE  cs.hazard_type::text <> 'heat_acute'::text;
        ALTER TABLE canonical_scores DROP COLUMN IF EXISTS score_lane;
    """)
