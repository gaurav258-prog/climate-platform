"""seismic_tables

Revision ID: a1b2c3d4e5f6
Revises: 80739a9ddc61
Create Date: 2026-06-25

Adds two tables for the seismic hazard module:
  - seismic_events: normalised earthquake catalog (EMSC + USGS)
  - damage_assessments: co-seismic SAR damage probability per H3 cell

The satellite_observations table (existing) stores raw EMSC observations and
static ESHM20 PGA values via the SEISMIC hazard_type — no schema change needed there.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '2ad712e08c57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Normalised earthquake event catalog
    # Populated by EMSCAdapter and monitor_seismic.py
    op.create_table(
        'seismic_events',
        sa.Column('event_id', sa.Text(), nullable=False),
        sa.Column('magnitude', sa.Numeric(4, 2), nullable=False),
        sa.Column('mag_type', sa.String(10), nullable=True),
        sa.Column('depth_km', sa.Numeric(7, 2), nullable=True),
        sa.Column('epicentre_lat', sa.Numeric(8, 5), nullable=False),
        sa.Column('epicentre_lon', sa.Numeric(8, 5), nullable=False),
        sa.Column('epicentre_h3', sa.String(20), nullable=True),
        sa.Column('origin_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('region_name', sa.Text(), nullable=True),
        sa.Column('source_catalog', sa.String(50), nullable=True),  # 'EMSC', 'USGS'
        sa.Column('review_status', sa.String(20), nullable=True),   # 'reviewed', 'preliminary', 'automatic'
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('damage_assessment_status', sa.String(30), nullable=True),  # 'pending', 'complete', 'insufficient_data'
        sa.PrimaryKeyConstraint('event_id'),
    )
    op.create_index('idx_seismic_events_origin', 'seismic_events', ['origin_time'], postgresql_using='btree')
    op.create_index('idx_seismic_events_magnitude', 'seismic_events', ['magnitude'], postgresql_using='btree')
    op.create_index('idx_seismic_events_epicentre', 'seismic_events', ['epicentre_h3'], postgresql_using='btree')

    # Co-seismic SAR damage assessment results
    # One row per (event × H3 cell) with damage probability from SAR intensity change
    op.create_table(
        'damage_assessments',
        sa.Column('assessment_id', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('event_id', sa.Text(), sa.ForeignKey('seismic_events.event_id', ondelete='CASCADE'), nullable=False),
        sa.Column('h3_cell', sa.String(20), nullable=False),
        sa.Column('damage_probability', sa.Numeric(5, 4), nullable=False),  # 0.0000–1.0000
        sa.Column('log_ratio_db', sa.Numeric(8, 4), nullable=True),        # dB change pre→post
        sa.Column('confidence', sa.String(10), nullable=True),              # 'high'/'medium'/'low'
        sa.Column('distance_km', sa.Numeric(7, 2), nullable=True),          # from epicentre
        sa.Column('method', sa.String(50), nullable=True),                  # 'sar_intensity_change_grd'
        sa.Column('pre_pass_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('post_pass_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assessed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('assessment_id'),
        sa.UniqueConstraint('event_id', 'h3_cell', name='uq_damage_event_cell'),
    )
    op.create_index('idx_damage_event', 'damage_assessments', ['event_id'], postgresql_using='btree')
    op.create_index('idx_damage_cell', 'damage_assessments', ['h3_cell'], postgresql_using='btree')
    op.create_index('idx_damage_probability', 'damage_assessments', ['damage_probability'], postgresql_using='btree')


def downgrade() -> None:
    op.drop_table('damage_assessments')
    op.drop_table('seismic_events')
