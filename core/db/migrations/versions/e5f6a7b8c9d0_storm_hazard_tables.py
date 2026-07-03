"""storm_hazard_tables

Revision ID: e5f6a7b8c9d0
Revises: d3e4f5a6b7c8
Create Date: 2026-07-03

Adds storm_events: a normalised tropical-cyclone TRACK catalog (IBTrACS), one row
per 6-hourly track observation. A storm is neither a fixed point (seismic epicentre,
volcano vent) nor a smooth climate field (heat/drought) — it's a moving track. This
schema treats each track observation as its own event, the same way seismic_events
already treats each aftershock in a sequence as its own row; scripts/score_storm_event.py
scores every observation and takes the MAX hazard per H3 cell across the whole track
(the exact "max over multiple events" pattern score_seismic_event.py already uses).

Unlike volcanic, no separate curated hazard-zone table is needed: IBTrACS carries the
radius of maximum winds (RMW) directly on each track observation when available.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'storm_events',
        sa.Column('event_id', sa.Text(), nullable=False),
        sa.Column('storm_id', sa.String(20), nullable=False),      # IBTrACS SID, e.g. '2017260N15300'
        sa.Column('storm_name', sa.Text(), nullable=False),
        sa.Column('season_year', sa.Integer(), nullable=True),
        sa.Column('basin', sa.String(4), nullable=True),           # 'NA', 'WP', etc.
        sa.Column('observation_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lat', sa.Numeric(8, 5), nullable=False),
        sa.Column('lon', sa.Numeric(8, 5), nullable=False),
        sa.Column('h3_cell', sa.String(20), nullable=True),
        sa.Column('max_wind_kt', sa.Numeric(6, 2), nullable=True),    # USA_WIND, knots
        sa.Column('central_pressure_mb', sa.Numeric(7, 2), nullable=True),
        sa.Column('rmw_km', sa.Numeric(7, 2), nullable=True),         # USA_RMW converted nmile->km
        sa.Column('sshs_category', sa.SmallInteger(), nullable=True), # USA_SSHS, -1..5
        sa.Column('source_catalog', sa.String(50), nullable=True),    # 'IBTrACS'
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('event_id'),
    )
    op.create_index('idx_storm_events_storm', 'storm_events', ['storm_id'], postgresql_using='btree')
    op.create_index('idx_storm_events_h3', 'storm_events', ['h3_cell'], postgresql_using='btree')
    op.create_index('idx_storm_events_time', 'storm_events', ['observation_time'], postgresql_using='btree')


def downgrade() -> None:
    op.drop_table('storm_events')
