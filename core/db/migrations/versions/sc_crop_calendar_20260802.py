"""WS4b — crop-calendar drought/soil-water overlay so two crops can share one belt.

THE PROBLEM. A cell's drought score in `canonical_scores` is computed over a specific
crop's growing-season window (season months + SPEI scale). Two crops on the SAME belt
want DIFFERENT windows (e.g. Morocco wheat Jan–Apr/SPEI-3 vs Morocco barley Jan–Jun/SPEI-6),
but `canonical_scores` holds one active row per (cell, hazard) — so scoring the second crop
would RETIRE the first's reading. `canonical_scores` is also read+aggregated by every
financial/regulatory path on `h3_cell`; a second active drought row there would silently
double-count those numbers.

THE FIX (additive, zero blast radius). Leave `canonical_scores` strictly one-active-row-per
(cell, hazard) — the GENERIC lane every non-agri reader keeps using, untouched. Add a small
`sc_crop_calendar_score` OVERLAY holding the per-crop-calendar drought/soil-water score + the
CMIP6 band, keyed by (commodity, origin, cell, hazard, scenario, horizon). ONLY the agri plot
view reads it, preferring the crop's own row and falling back to the generic reading. Wheat and
barley each get their own overlay slot, so neither can overwrite the other. Append-only like
`canonical_scores` (retire via valid_to; payload immutable; DELETE blocked).

Revision ID: sc_crop_calendar_202608
Revises: sc_plot_ci_202608
"""
from alembic import op

revision = "sc_crop_calendar_202608"
down_revision = "sc_plot_ci_202608"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE sc_crop_calendar_score (
        score_id        uuid NOT NULL,
        commodity_id    uuid NOT NULL,
        origin          varchar NOT NULL,
        h3_cell         varchar NOT NULL,
        h3_resolution   smallint,
        hazard_type     varchar NOT NULL,
        scenario        varchar NOT NULL,
        time_horizon    varchar NOT NULL,
        risk_score      numeric NOT NULL,
        risk_bucket     varchar,
        score_ci_lower  numeric,
        score_ci_upper  numeric,
        season_months   varchar,
        spei_scale      smallint,
        model_version   varchar,
        data_vintage    timestamptz,
        scored_at       timestamptz NOT NULL,
        valid_from      timestamptz,
        valid_to        timestamptz,
        PRIMARY KEY (score_id, scored_at)
    );
    """)
    # one active row per crop-calendar × cell × scenario × horizon (retire the rest via valid_to)
    op.execute("""
    CREATE INDEX ix_crop_calendar_current
        ON sc_crop_calendar_score (commodity_id, origin, h3_cell, hazard_type, scenario, time_horizon)
        WHERE valid_to IS NULL;
    """)

    # append-only guard, mirroring prevent_canonical_score_mutation: only retirement (valid_to) allowed
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_crop_calendar_mutation()
    RETURNS trigger LANGUAGE plpgsql AS $fn$
    DECLARE chk sc_crop_calendar_score;
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'sc_crop_calendar_score is append-only: DELETE is not permitted';
        END IF;
        IF OLD.valid_to IS NOT NULL THEN
            RAISE EXCEPTION 'sc_crop_calendar_score: retired rows are immutable';
        END IF;
        IF NEW.valid_to IS NULL THEN
            RAISE EXCEPTION 'sc_crop_calendar_score is append-only: only setting valid_to (retirement) is permitted';
        END IF;
        chk := NEW; chk.valid_to := OLD.valid_to;
        IF chk IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'sc_crop_calendar_score: payload is immutable; only valid_to may change';
        END IF;
        RETURN NEW;
    END;
    $fn$;
    """)
    op.execute("""
    CREATE TRIGGER prevent_delete_crop_calendar BEFORE DELETE ON sc_crop_calendar_score
        FOR EACH ROW EXECUTE FUNCTION prevent_crop_calendar_mutation();
    """)
    op.execute("""
    CREATE TRIGGER prevent_update_crop_calendar BEFORE UPDATE ON sc_crop_calendar_score
        FOR EACH ROW EXECUTE FUNCTION prevent_crop_calendar_mutation();
    """)

    # plot view: overlay the crop-calendar reading (score + band) onto the generic canonical spine.
    # COALESCE(cal.*, cs.*) → a plot reads ITS crop's calendar where one exists, else the generic
    # reading (backward-compatible: no overlay rows yet ⇒ identical to before). At most one active
    # overlay row per key (unique index), so no duplicate rows / no double-count.
    op.execute("DROP VIEW IF EXISTS v_sc_plot_physical_risk;")
    op.execute("""
    CREATE VIEW v_sc_plot_physical_risk AS
    SELECT p.org_id,
           p.plot_id,
           p.supplier_id,
           p.commodity_id,
           p.h3_cell,
           cs.hazard_type,
           COALESCE(cal.risk_score, cs.risk_score)::double precision        AS physical_risk_score,
           cs.scenario,
           cs.time_horizon,
           COALESCE(cal.model_version, cs.model_version)                    AS model_version,
           COALESCE(cal.scored_at, cs.scored_at)                            AS scored_at,
           COALESCE(cal.score_ci_lower, cs.score_ci_lower)::double precision AS physical_risk_ci_lower,
           COALESCE(cal.score_ci_upper, cs.score_ci_upper)::double precision AS physical_risk_ci_upper
    FROM sc_sourcing_plots p
    JOIN canonical_scores cs
      ON cs.h3_cell::text = p.h3_cell::text
     AND cs.valid_to IS NULL
     AND cs.score_lane::text = 'standing'::text
    LEFT JOIN sc_crop_calendar_score cal
      ON cal.h3_cell::text = p.h3_cell::text
     AND cal.commodity_id = p.commodity_id
     AND cal.origin::text = p.country::text
     AND cal.hazard_type::text = cs.hazard_type::text
     AND cal.scenario::text = cs.scenario::text
     AND cal.time_horizon::text = cs.time_horizon::text
     AND cal.valid_to IS NULL;
    """)


def downgrade() -> None:
    # restore the pre-overlay plot view (WS4a shape)
    op.execute("DROP VIEW IF EXISTS v_sc_plot_physical_risk;")
    op.execute("""
    CREATE VIEW v_sc_plot_physical_risk AS
    SELECT p.org_id, p.plot_id, p.supplier_id, p.commodity_id, p.h3_cell,
           cs.hazard_type,
           cs.risk_score::double precision AS physical_risk_score,
           cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at,
           cs.score_ci_lower::double precision AS physical_risk_ci_lower,
           cs.score_ci_upper::double precision AS physical_risk_ci_upper
    FROM sc_sourcing_plots p
    JOIN canonical_scores cs
      ON cs.h3_cell::text = p.h3_cell::text
     AND cs.valid_to IS NULL
     AND cs.score_lane::text = 'standing'::text;
    """)
    op.execute("DROP TRIGGER IF EXISTS prevent_delete_crop_calendar ON sc_crop_calendar_score;")
    op.execute("DROP TRIGGER IF EXISTS prevent_update_crop_calendar ON sc_crop_calendar_score;")
    op.execute("DROP FUNCTION IF EXISTS prevent_crop_calendar_mutation();")
    op.execute("DROP TABLE IF EXISTS sc_crop_calendar_score;")
