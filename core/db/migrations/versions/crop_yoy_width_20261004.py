"""A year-on-year change can exceed ±999,999.99 % (E161).

numeric(8,2) held the national figures, but a county series moves from a few tonnes to thousands (a South Dakota county's
barley: +1,052,100 % from 1934 to 1935) — true arithmetic on the publisher's figures that the column could not hold,
so the county release could not be staged. Widened to numeric(12,2) in the store and in release rows. Downgrade refuses
while a held value needs the wider column.

Revision ID: crop_yoy_width_20261004
Revises: calib_pipeline_20261004
"""
from typing import Sequence, Union

from alembic import op

revision: str = "crop_yoy_width_20261004"
down_revision: Union[str, None] = "calib_pipeline_20261004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO crop_yield_observations (commodity, country, season_year, production_tonnes, yoy_change_pct, source)
                VALUES ('Probe', 'US', 2020, 1, 1052100.0, 'probe');""",
    "cleanup": """DELETE FROM crop_yield_observations WHERE source = 'probe';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crop_yield_observations ALTER COLUMN yoy_change_pct TYPE numeric(12,2);
        ALTER TABLE crop_yield_release_rows ALTER COLUMN yoy_change_pct TYPE numeric(12,2);
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM crop_yield_observations WHERE abs(yoy_change_pct) >= 1000000)
             OR EXISTS (SELECT 1 FROM crop_yield_release_rows WHERE abs(yoy_change_pct) >= 1000000) THEN
            RAISE EXCEPTION 'crop_yoy_width_20261004 downgrade: a held year-on-year change needs the wider column';
          END IF;
        END $$;
        ALTER TABLE crop_yield_observations ALTER COLUMN yoy_change_pct TYPE numeric(8,2);
        ALTER TABLE crop_yield_release_rows ALTER COLUMN yoy_change_pct TYPE numeric(8,2);
    """)
