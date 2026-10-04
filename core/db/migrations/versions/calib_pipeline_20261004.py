"""One calibration pipeline: every crop calibration is a recorded recipe, every evaluation a recorded run (E162).

Before this revision a calibration was hand-assembled: a script fitted it and upserted sc_commodity_fit, which kept no
record of the production series it read, whether the cycle was removed, or the recipe it came from — the calibration
audit had to guess the source by trying every series (champion_oos.reconstruct), and the calibration row could keep a
season its own fit no longer used (persist_fit's COALESCE).

  crop_calibration_specs   the recipe of one calibration slot (crop × origin × yield region × driver), fixed before it
                           is fitted: the yield series (store source + region), the weather (a named box, or the crop's
                           own growing area), the season (harvest-year months and any previous-year months), the SPEI
                           scale, whether the bearing cycle is removed, and why (basis). One active recipe per slot.
  crop_calibration_runs    one evaluation of a recipe on the data of the day: the fit, the downside gate (r²_oos), the
                           upside gate (the four rules agreed 2026-10-04), the inputs it read, its ledger entry. A run's
                           figures never change; only its status moves recorded → proposed → published | rejected,
                           and published → superseded when a later run of the same recipe is published.
  sc_commodity_fit         gains yield_source, yield_region, allow_cycle, spec_id, run_id — a published fit names
                           what it was fitted on.
  permission calibration.review   decide a calibration publication (platform operator).

Downgrade refuses while a recipe is recorded.

Revision ID: calib_pipeline_20261004
Revises: crop_region_20261004
"""
from typing import Sequence, Union

from alembic import op

revision: str = "calib_pipeline_20261004"
down_revision: Union[str, None] = "crop_region_20261004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO crop_calibration_specs (commodity, origin, yield_source, driver, weather_kind, weather_key,
                    season_months, allow_cycle, basis, protocol)
                VALUES ('Probe', 'ZZ', 'probe', 'drought', 'box', 'probe', '{1}', false, 'probe', 'probe');""",
    "cleanup": """DELETE FROM crop_calibration_specs WHERE commodity = 'Probe';""",
}


def upgrade() -> None:
    op.execute("""
        CREATE TABLE crop_calibration_specs (
            spec_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            commodity           varchar(80) NOT NULL,
            origin              varchar(3) NOT NULL,
            yield_source        varchar(200) NOT NULL,
            yield_region        varchar(24) NOT NULL DEFAULT '',
            driver              varchar(32) NOT NULL CHECK (driver IN ('drought', 'heat', 'soil_water')),
            weather_kind        varchar(16) NOT NULL CHECK (weather_kind IN ('box', 'crop_area')),
            weather_key         varchar(120) NOT NULL,
            season_months       integer[] NOT NULL CHECK (cardinality(season_months) > 0),
            season_prev_months  integer[] NOT NULL DEFAULT '{}',
            spei_scale          integer NOT NULL DEFAULT 6 CHECK (spei_scale BETWEEN 1 AND 24),
            allow_cycle         boolean NOT NULL,
            basis               text NOT NULL,
            protocol            varchar(40) NOT NULL,
            created_at          timestamptz NOT NULL DEFAULT now(),
            retired_at          timestamptz,
            retired_reason      text,
            CHECK ((retired_at IS NULL) = (retired_reason IS NULL))
        );
        CREATE UNIQUE INDEX ux_crop_calibration_spec_active ON crop_calibration_specs
            (commodity, origin, yield_region, driver) WHERE retired_at IS NULL;

        CREATE FUNCTION guard_crop_calibration_spec() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (NEW.commodity, NEW.origin, NEW.yield_source, NEW.yield_region, NEW.driver, NEW.weather_kind,
                NEW.weather_key, NEW.season_months, NEW.season_prev_months, NEW.spei_scale, NEW.allow_cycle, NEW.basis,
                NEW.protocol, NEW.created_at)
               IS DISTINCT FROM
               (OLD.commodity, OLD.origin, OLD.yield_source, OLD.yield_region, OLD.driver, OLD.weather_kind,
                OLD.weather_key, OLD.season_months, OLD.season_prev_months, OLD.spei_scale, OLD.allow_cycle, OLD.basis,
                OLD.protocol, OLD.created_at)
               OR (OLD.retired_at IS NOT NULL AND NEW.retired_at IS DISTINCT FROM OLD.retired_at) THEN
                RAISE EXCEPTION 'a calibration recipe never changes — a new recipe replaces it (only retirement is set)';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER trg_crop_calibration_specs_guard BEFORE UPDATE ON crop_calibration_specs
            FOR EACH ROW EXECUTE FUNCTION guard_crop_calibration_spec();

        CREATE TABLE crop_calibration_runs (
            run_id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                 bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
            spec_id             uuid NOT NULL REFERENCES crop_calibration_specs(spec_id),
            run_at              timestamptz NOT NULL DEFAULT now(),
            inputs              jsonb NOT NULL,
            outcome             varchar(16) NOT NULL CHECK (outcome IN ('fitted', 'no_panel', 'too_few_years')),
            reason              text,
            n_years             integer,
            baseline_from       integer,
            baseline_to         integer,
            slope               numeric(12,5),
            intercept           numeric(12,5),
            r2                  numeric(6,4),
            r2_oos              numeric(7,4),
            rmse                numeric(12,5),
            score_mean          numeric(12,5),
            score_sxx           numeric(18,5),
            band_cov68          numeric(5,4),
            downside_pass       boolean NOT NULL,
            upside              jsonb,
            upside_pass         boolean NOT NULL,
            validation_run_id   uuid,
            status              varchar(12) NOT NULL DEFAULT 'recorded'
                                CHECK (status IN ('recorded', 'proposed', 'published', 'superseded', 'rejected')),
            approval_request_id uuid REFERENCES approval_requests(request_id),
            decided_by          uuid REFERENCES users(user_id),
            decided_at          timestamptz,
            decision_reason     text,
            CHECK ((outcome = 'fitted') = (r2_oos IS NOT NULL)),
            CHECK (outcome = 'fitted' OR NOT (downside_pass OR upside_pass)),
            CHECK (status IN ('recorded', 'proposed') OR decided_at IS NOT NULL)
        );
        CREATE INDEX ix_crop_calibration_runs_spec ON crop_calibration_runs (spec_id, seq);
        CREATE UNIQUE INDEX ux_crop_calibration_run_published ON crop_calibration_runs (spec_id)
            WHERE status = 'published';

        CREATE FUNCTION guard_crop_calibration_run() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'crop_calibration_runs is append-only: a run is the record of one evaluation';
            END IF;
            IF (NEW.spec_id, NEW.run_at, NEW.inputs, NEW.outcome, NEW.reason, NEW.n_years, NEW.baseline_from,
                NEW.baseline_to, NEW.slope, NEW.intercept, NEW.r2, NEW.r2_oos, NEW.rmse, NEW.score_mean, NEW.score_sxx,
                NEW.band_cov68, NEW.downside_pass, NEW.upside, NEW.upside_pass, NEW.validation_run_id)
               IS DISTINCT FROM
               (OLD.spec_id, OLD.run_at, OLD.inputs, OLD.outcome, OLD.reason, OLD.n_years, OLD.baseline_from,
                OLD.baseline_to, OLD.slope, OLD.intercept, OLD.r2, OLD.r2_oos, OLD.rmse, OLD.score_mean, OLD.score_sxx,
                OLD.band_cov68, OLD.downside_pass, OLD.upside, OLD.upside_pass, OLD.validation_run_id) THEN
                RAISE EXCEPTION 'a calibration run''s figures never change — only its status and decision';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER trg_crop_calibration_runs_guard BEFORE UPDATE OR DELETE ON crop_calibration_runs
            FOR EACH ROW EXECUTE FUNCTION guard_crop_calibration_run();

        ALTER TABLE sc_commodity_fit
            ADD COLUMN yield_source varchar(200),
            ADD COLUMN yield_region varchar(24),
            ADD COLUMN allow_cycle  boolean,
            ADD COLUMN spec_id      uuid REFERENCES crop_calibration_specs(spec_id),
            ADD COLUMN run_id       uuid REFERENCES crop_calibration_runs(run_id);

        INSERT INTO permissions (code, description)
        VALUES ('calibration.review', 'Tellumen platform operator — decide the publication of a crop calibration '
                                      '(its downside and upside verdicts) recorded by the calibration pipeline')
        ON CONFLICT (code) DO NOTHING;
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id FROM roles r JOIN organizations o ON o.org_id = r.org_id
        JOIN permissions p ON p.code = 'calibration.review'
        WHERE o.type = 'platform' AND r.name = 'platform-operator'
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM crop_calibration_specs) THEN
            RAISE EXCEPTION 'calib_pipeline_20261004 downgrade: calibration recipes are recorded — no table before '
                            'this revision keeps them or their runs';
          END IF;
        END $$;
        DELETE FROM role_permissions rp USING permissions p
        WHERE p.permission_id = rp.permission_id AND p.code = 'calibration.review';
        DELETE FROM permissions WHERE code = 'calibration.review';
        ALTER TABLE sc_commodity_fit DROP COLUMN run_id, DROP COLUMN spec_id, DROP COLUMN allow_cycle,
            DROP COLUMN yield_region, DROP COLUMN yield_source;
        DROP TABLE crop_calibration_runs;
        DROP FUNCTION guard_crop_calibration_run();
        DROP TABLE crop_calibration_specs;
        DROP FUNCTION guard_crop_calibration_spec();
    """)
