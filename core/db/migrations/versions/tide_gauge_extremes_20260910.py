"""tide_gauge_extremes — observed monthly maximum and mean sea level at GESLA-3 tide gauges 1979–2020: the site
extreme-still-water term of the coastal-flood channel and the target it is held out against in time.

Revision ID: tide_gauge_extremes_20260910
Revises: storm_events_latlon_20260910
"""
from typing import Sequence, Union

from alembic import op

revision: str = "tide_gauge_extremes_20260910"
down_revision: Union[str, None] = "storm_events_latlon_20260910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS tide_gauge_extremes (
            record_id     TEXT NOT NULL,                -- GESLA record id (one station may hold several)
            station_name  TEXT,
            country       TEXT,                        -- ISO 3166-1 alpha-3
            agency        TEXT,
            lat           DOUBLE PRECISION NOT NULL,
            lon           DOUBLE PRECISION NOT NULL,
            year          INTEGER NOT NULL,
            month         INTEGER NOT NULL,
            max_m         DOUBLE PRECISION NOT NULL,   -- monthly maximum hourly level, provider datum
            mean_m        DOUBLE PRECISION NOT NULL,   -- monthly mean hourly level, same datum
            dist_to_coast_km DOUBLE PRECISION,         -- GESLA holds river/marsh gauges too; the channel reads sea gauges only
            PRIMARY KEY (record_id, year, month)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_tide_gauge_extremes_latlon ON tide_gauge_extremes (lat, lon)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tide_gauge_extremes")
