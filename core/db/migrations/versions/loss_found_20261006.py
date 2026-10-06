"""The loss foundation's data model (E169): hazard intensity in physical units by return period, what a building is
used for, loss runs with their results and exceedance curves, and the building each asset stands on.

Until now every hazard was held only as a 0–100 ranking of places (canonical_scores), so no loss could be computed
from the hazard itself: the money figures rest on the institution's stated damage ratio and event probability by score
band (ml.scoring.damage_function, E69). The depth, wind and gust data the platform already holds by return period
(JRC river-flood depth at 1-in-10/100/500, STORM's 10,000 synthetic cyclone years) were folded into scores and their
physical values discarded.

  hazard_intensity_samples  the intensity at a point for one layer and return period, in the layer's unit
                            (data/reference/hazard_intensity_layers.json): the value at the point, and over the point's
                            H3 res-8 cell the share with any intensity and its mean. Outside a layer's coverage the row
                            says so (no value), never a zero. Append-only; a new layer version adds new rows.
  occupancy                 what an asset is used for, as the institution states it, on portfolio_entities and
                            sc_company_sites — the classes of the damage curves (data/reference/occupancy.json).
  loss_runs                 one loss computation for an organisation's book: the scenario and horizon, the layers, event
                            sets and damage curves it read, the crosswalk and method it used. Never changes.
  loss_results              per asset and peril: the exposed value, the curve, the expected annual loss and the loss at
                            each return period — or the named gap that stopped it. Never changes.
  loss_ep_points            the book's exceedance curve per peril (annual aggregate and occurrence), and on what basis
                            the assets' losses were combined (an event set, or the institution's stated dependence).
  asset_building_matches    the building footprint an asset was matched to (or that none was within reach), per source
                            version. Append-only; the latest match is the highest match_id.

Downgrade refuses while a loss run, an intensity sample or a building match is recorded.

Revision ID: loss_found_20261006
Revises: crop_weather_20261005
"""
from typing import Sequence, Union

from alembic import op

revision: str = "loss_found_20261006"
down_revision: Union[str, None] = "crop_weather_20261005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OCCUPANCY = ("residential", "commercial", "industrial", "transport", "infrastructure", "agriculture")
SCENARIOS = ("baseline", "orderly_1_5c", "disorderly_2c", "hot_house_3_5c")
HORIZONS = ("current", "2030", "2050", "2100")
def _in(vals: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in vals) + ")"

REFUSAL_PROBE = {
    "setup": """INSERT INTO hazard_intensity_samples (layer_key, layer_version, latitude, longitude, h3_cell, rp_years,
                    status) VALUES ('probe', 'probe', 0, 0, 'probe', 10, 'outside_coverage');""",
    "cleanup": """ALTER TABLE hazard_intensity_samples DISABLE TRIGGER trg_hazard_intensity_samples_guard;
                  DELETE FROM hazard_intensity_samples WHERE layer_key = 'probe';
                  ALTER TABLE hazard_intensity_samples ENABLE TRIGGER trg_hazard_intensity_samples_guard;""",
}


def _append_only(table: str, what: str) -> str:
    return f"""
        CREATE FUNCTION guard_{table}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '{table} is append-only: {what}';
        END $$;
        CREATE TRIGGER trg_{table}_guard BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION guard_{table}();"""


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE hazard_intensity_samples (
            sample_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            layer_key       varchar(64) NOT NULL,
            layer_version   varchar(40) NOT NULL,
            latitude        double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
            longitude       double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
            h3_cell         varchar(20) NOT NULL,
            rp_years        integer NOT NULL CHECK (rp_years > 1),
            status          varchar(16) NOT NULL CHECK (status IN ('sampled', 'outside_coverage')),
            value           double precision CHECK (value >= 0),
            cell_fraction   double precision CHECK (cell_fraction BETWEEN 0 AND 1),
            cell_mean       double precision CHECK (cell_mean >= 0),
            sampled_at      timestamptz NOT NULL DEFAULT now(),
            CHECK ((status = 'sampled') = (value IS NOT NULL)),
            CHECK (status = 'sampled' OR (cell_fraction IS NULL AND cell_mean IS NULL))
        );
        CREATE UNIQUE INDEX ux_hazard_intensity_sample ON hazard_intensity_samples
            (layer_key, layer_version, latitude, longitude, rp_years);
        CREATE INDEX ix_hazard_intensity_cell ON hazard_intensity_samples (h3_cell, layer_key, layer_version);
        {_append_only("hazard_intensity_samples", "a new layer version adds new rows")}

        ALTER TABLE portfolio_entities ADD COLUMN occupancy varchar(20) CHECK (occupancy IN {_in(OCCUPANCY)});
        ALTER TABLE sc_company_sites ADD COLUMN occupancy varchar(20) CHECK (occupancy IN {_in(OCCUPANCY)});

        CREATE TABLE loss_runs (
            run_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq             bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
            org_id          uuid NOT NULL REFERENCES organizations(org_id),
            book            varchar(32) NOT NULL CHECK (book IN ('banking', 'insurance', 'insurer_investments',
                                                                  'realestate', 'assetmgmt', 'company_sites')),
            scenario        varchar(32) NOT NULL CHECK (scenario IN {_in(SCENARIOS)}),
            time_horizon    varchar(16) NOT NULL CHECK (time_horizon IN {_in(HORIZONS)}),
            as_of           date NOT NULL,
            engine_version  varchar(40) NOT NULL,
            inputs          jsonb NOT NULL,
            n_assets        integer NOT NULL CHECK (n_assets >= 0),
            n_gaps          integer NOT NULL CHECK (n_gaps BETWEEN 0 AND n_assets),
            created_by      uuid REFERENCES users(user_id),
            created_at      timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_loss_runs_org ON loss_runs (org_id, book, seq);
        {_append_only("loss_runs", "a loss run is the record of one computation")}

        CREATE TABLE loss_results (
            run_id              uuid NOT NULL REFERENCES loss_runs(run_id),
            asset_kind          varchar(20) NOT NULL CHECK (asset_kind IN ('portfolio_entity', 'company_site')),
            asset_id            uuid NOT NULL,
            peril               varchar(32) NOT NULL,
            exposed_value_eur   numeric(18,2) CHECK (exposed_value_eur >= 0),
            occupancy           varchar(20) CHECK (occupancy IN {_in(OCCUPANCY)}),
            curve_key           varchar(80),
            eal_eur             numeric(18,2) CHECK (eal_eur >= 0),
            loss_at_rp          jsonb,
            gap                 text,
            PRIMARY KEY (run_id, asset_kind, asset_id, peril),
            CHECK ((gap IS NULL) = (eal_eur IS NOT NULL)),
            CHECK (gap IS NOT NULL OR (curve_key IS NOT NULL AND exposed_value_eur IS NOT NULL AND loss_at_rp IS NOT NULL))
        );
        {_append_only("loss_results", "results belong to their run")}

        CREATE TABLE loss_ep_points (
            run_id      uuid NOT NULL REFERENCES loss_runs(run_id),
            peril       varchar(32) NOT NULL,
            kind        varchar(4) NOT NULL CHECK (kind IN ('aep', 'oep')),
            rp_years    integer NOT NULL CHECK (rp_years > 1),
            loss_eur    numeric(18,2) NOT NULL CHECK (loss_eur >= 0),
            basis       varchar(24) NOT NULL CHECK (basis IN ('event_set', 'stated_dependence')),
            PRIMARY KEY (run_id, peril, kind, rp_years)
        );
        {_append_only("loss_ep_points", "a curve belongs to its run")}

        CREATE TABLE asset_building_matches (
            match_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            asset_kind          varchar(20) NOT NULL CHECK (asset_kind IN ('portfolio_entity', 'company_site')),
            asset_id            uuid NOT NULL,
            source_key          varchar(64) NOT NULL,
            source_version      varchar(40) NOT NULL,
            status              varchar(20) NOT NULL CHECK (status IN ('matched', 'no_building', 'outside_coverage')),
            building_ref        text,
            footprint_area_m2   double precision CHECK (footprint_area_m2 > 0),
            height_m            double precision CHECK (height_m > 0),
            distance_m          double precision CHECK (distance_m >= 0),
            matched_at          timestamptz NOT NULL DEFAULT now(),
            CHECK ((status = 'matched') = (building_ref IS NOT NULL AND footprint_area_m2 IS NOT NULL
                                           AND distance_m IS NOT NULL))
        );
        CREATE INDEX ix_asset_building_matches_asset ON asset_building_matches (asset_kind, asset_id, match_id);
        {_append_only("asset_building_matches", "a new match is a new row; the latest is the highest match_id")}
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM loss_runs) OR EXISTS (SELECT 1 FROM hazard_intensity_samples)
               OR EXISTS (SELECT 1 FROM asset_building_matches) THEN
                RAISE EXCEPTION 'loss runs, intensity samples or building matches are recorded — the loss foundation '
                                'cannot be removed without discarding them';
            END IF;
        END $$;
        DROP TABLE asset_building_matches;
        DROP FUNCTION guard_asset_building_matches();
        DROP TABLE loss_ep_points;
        DROP FUNCTION guard_loss_ep_points();
        DROP TABLE loss_results;
        DROP FUNCTION guard_loss_results();
        DROP TABLE loss_runs;
        DROP FUNCTION guard_loss_runs();
        ALTER TABLE sc_company_sites DROP COLUMN occupancy;
        ALTER TABLE portfolio_entities DROP COLUMN occupancy;
        DROP TABLE hazard_intensity_samples;
        DROP FUNCTION guard_hazard_intensity_samples();
    """)
