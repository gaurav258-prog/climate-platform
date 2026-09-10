"""station_extremes — observed 1991–2020 daily-record extremes at GHCN-Daily stations: the independent target for
backtesting the cold-wave, chronic-heat and heavy-precipitation channels (station observations are independent
of the reanalysis and climatology fields those channels are built from).

Revision ID: station_extremes_20260910
Revises: prisk_view_pushdown_20260910
"""
from typing import Sequence, Union

from alembic import op

revision: str = "station_extremes_20260910"
down_revision: Union[str, None] = "prisk_view_pushdown_20260910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS station_extremes (
            station_id        TEXT PRIMARY KEY,
            name              TEXT,
            region            TEXT NOT NULL,            -- EU | US
            latitude          DOUBLE PRECISION NOT NULL,
            longitude         DOUBLE PRECISION NOT NULL,
            h3_cell           TEXT NOT NULL,
            n_years           INTEGER NOT NULL,
            coldest_1in10_c   DOUBLE PRECISION,          -- 10th percentile of the annual minimum daily Tmin
            design_c          DOUBLE PRECISION,          -- 0.4th percentile of daily Tmin (99.6 % heating design)
            tmax_annual_max_c DOUBLE PRECISION,          -- mean of the annual maximum daily Tmax
            hot_days_per_yr   DOUBLE PRECISION,          -- days with Tmax ≥ 30 °C per year
            prcp_1day_max_mm  DOUBLE PRECISION,          -- mean of the annual maximum 1-day precipitation
            prcp_p99_mm       DOUBLE PRECISION,          -- 99th percentile of wet-day precipitation
            source            TEXT NOT NULL,
            fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS station_extremes")
