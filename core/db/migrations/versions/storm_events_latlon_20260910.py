"""Index storm_events (lat, lon) — the point scorer's track box was a full scan of the 45-year record per cell.

Revision ID: storm_events_latlon_20260910
Revises: station_extremes_20260910
"""
from typing import Sequence, Union

from alembic import op

revision: str = "storm_events_latlon_20260910"
down_revision: Union[str, None] = "station_extremes_20260910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_storm_events_latlon ON storm_events (lat, lon)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_storm_events_latlon")
