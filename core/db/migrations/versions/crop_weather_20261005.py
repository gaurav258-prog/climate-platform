"""Weather over each crop's own growing area, from the global ERA5-Land files — one weather source for every calibration
(E163).

  crop_weather_builds    one per build of the monthly panels: what it read (ERA5-Land files and years, crop-map weights,
                         boxes, SPEI scale, normal), first and last month
  crop_weather_targets   per build, each target ('crop:<commodity>:<origin>' — the crop's harvested area in the origin; or
                         'box:<region>' — a named box, equal weights): its cells and total weight
  crop_weather_monthly   per build and target, each month's weighted mean SPEI-6 and temperature anomaly
  crop_calibration_coverage   every crop × origin the crop maps hold: its recipe, or why it has none (replaced whole on
                         each generation — a derived view of the registry, maps, seasons and yield series)

Builds are kept: a run records the build it read. Downgrade refuses while a build is recorded.

Revision ID: crop_weather_20261005
Revises: crop_yoy_width_20261004
"""
from typing import Sequence, Union

from alembic import op

revision: str = "crop_weather_20261005"
down_revision: Union[str, None] = "crop_yoy_width_20261004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO crop_weather_builds (inputs, first_month, last_month) VALUES ('{}', '1991-01-01', '1991-01-01');""",
    "cleanup": """DELETE FROM crop_weather_builds WHERE inputs = '{}';""",
}


def upgrade() -> None:
    op.execute("""
        CREATE TABLE crop_weather_builds (
            build_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq          bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
            built_at     timestamptz NOT NULL DEFAULT now(),
            inputs       jsonb NOT NULL,
            first_month  date NOT NULL,
            last_month   date NOT NULL,
            CHECK (last_month >= first_month)
        );
        CREATE TABLE crop_weather_targets (
            build_id  uuid NOT NULL REFERENCES crop_weather_builds(build_id),
            target    varchar(140) NOT NULL,
            cells     integer NOT NULL CHECK (cells > 0),
            weight    numeric(16,1) NOT NULL,
            PRIMARY KEY (build_id, target)
        );
        CREATE INDEX ix_crop_weather_targets_target ON crop_weather_targets (target);
        CREATE TABLE crop_weather_monthly (
            build_id   uuid NOT NULL,
            target     varchar(140) NOT NULL,
            month      date NOT NULL,
            spei6      numeric(9,5),
            temp_anom  numeric(9,5),
            PRIMARY KEY (build_id, target, month),
            FOREIGN KEY (build_id, target) REFERENCES crop_weather_targets(build_id, target)
        );
        CREATE TABLE crop_calibration_coverage (
            commodity     varchar(80) NOT NULL,
            origin        varchar(3) NOT NULL,
            area_ha       numeric(16,1) NOT NULL,
            area_share    numeric(7,6) NOT NULL,
            status        varchar(20) NOT NULL
                          CHECK (status IN ('recipe', 'no_yield_series', 'too_few_years', 'no_season')),
            reason        text,
            spec_id       uuid REFERENCES crop_calibration_specs(spec_id),
            generated_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (commodity, origin),
            CHECK ((status = 'recipe') = (spec_id IS NOT NULL)),
            CHECK ((status = 'recipe') = (reason IS NULL))
        );
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM crop_weather_builds) THEN
            RAISE EXCEPTION 'crop_weather_20261005 downgrade: weather builds are recorded — calibration runs read them';
          END IF;
        END $$;
        DROP TABLE crop_calibration_coverage;
        DROP TABLE crop_weather_monthly;
        DROP TABLE crop_weather_targets;
        DROP TABLE crop_weather_builds;
    """)
