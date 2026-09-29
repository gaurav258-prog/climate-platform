"""volcanic_hazard_tables

Revision ID: d3e4f5a6b7c8
Revises: b8c9d0e1f2a3
Create Date: 2026-07-03

Adds two tables for the volcanic hazard module (mirrors the seismic pattern —
a point-source event, not a smooth climate field):
  - volcanic_events: normalised eruption catalog (Smithsonian Global Volcanism
    Program), one row per known eruption of a tracked volcano
  - volcanic_hazard_zones: curated per-volcano hazard-zone radii (proximal
    destruction + ashfall), sourced from published USGS/INSIVUMEH/PHIVOLCS
    hazard maps where available, VEI-scaled defaults otherwise — there is no
    unified global API for these, so unlike seismic_events this is a small,
    honestly-labeled hand-curated table, not something live-ingested wholesale.

Also extends the hazard_type CHECK constraints (added in b7c1a2d3e4f5) to
include 'volcanic', from a vocabulary list frozen in this file (the
core.types.HAZARD_VALUES of the commit that added it).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Frozen vocabulary (self-contained migration — never import app code): core.types.HAZARD_VALUES as of commit 07320da.
_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic', 'volcanic',
)

# The vocabulary in force at down_revision (b7c1a2d3e4f5) — what downgrade() restores.
_PRIOR_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic',
)

revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _in_list(column: str, values) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    # Normalised eruption catalog — populated by scripts/ingest_gvp_volcanic.py
    op.create_table(
        'volcanic_events',
        sa.Column('event_id', sa.Text(), nullable=False),
        sa.Column('volcano_number', sa.Integer(), nullable=False),   # GVP volcano number
        sa.Column('volcano_name', sa.Text(), nullable=False),
        sa.Column('vei', sa.SmallInteger(), nullable=True),          # Volcanic Explosivity Index 0-8
        sa.Column('activity_type', sa.String(20), nullable=True),    # 'Confirmed' / 'Uncertain'
        sa.Column('start_year', sa.Integer(), nullable=True),
        sa.Column('start_month', sa.SmallInteger(), nullable=True),
        sa.Column('start_day', sa.SmallInteger(), nullable=True),
        sa.Column('end_year', sa.Integer(), nullable=True),
        sa.Column('end_month', sa.SmallInteger(), nullable=True),
        sa.Column('end_day', sa.SmallInteger(), nullable=True),
        sa.Column('epicentre_lat', sa.Numeric(8, 5), nullable=False),
        sa.Column('epicentre_lon', sa.Numeric(8, 5), nullable=False),
        sa.Column('epicentre_h3', sa.String(20), nullable=True),
        sa.Column('source_catalog', sa.String(50), nullable=True),   # 'GVP'
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('event_id'),
    )
    op.create_index('idx_volcanic_events_volcano', 'volcanic_events', ['volcano_number'], postgresql_using='btree')
    op.create_index('idx_volcanic_events_epicentre', 'volcanic_events', ['epicentre_h3'], postgresql_using='btree')
    op.create_index('idx_volcanic_events_start_year', 'volcanic_events', ['start_year'], postgresql_using='btree')

    # Curated per-volcano hazard-zone radii — see module docstring: no unified
    # global API exists for these, so this is hand-curated per backtest volcano.
    op.create_table(
        'volcanic_hazard_zones',
        sa.Column('zone_id', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('volcano_number', sa.Integer(), nullable=False),
        sa.Column('volcano_name', sa.Text(), nullable=False),
        sa.Column('zone_type', sa.String(20), nullable=False),        # 'proximal' | 'ashfall'
        sa.Column('radius_km', sa.Numeric(6, 2), nullable=False),
        sa.Column('vei_reference', sa.SmallInteger(), nullable=True), # VEI this radius was observed/published at
        sa.Column('source', sa.String(30), nullable=False),           # 'gvp_derived'|'usgs_published'|'fallback_estimate'
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('zone_id'),
        sa.UniqueConstraint('volcano_number', 'zone_type', name='uq_volcanic_zone_volcano_type'),
    )
    op.create_index('idx_volcanic_zones_volcano', 'volcanic_hazard_zones', ['volcano_number'], postgresql_using='btree')

    # Extend the hazard_type CHECK constraints to include 'volcanic' — drop and
    # re-add from the frozen _HAZARD_VALUES (now includes VOLCANIC).
    for table, name, column in [
        ("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"),
        ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, _HAZARD_VALUES)}) NOT VALID"
        )


def downgrade() -> None:
    op.drop_table('volcanic_hazard_zones')
    op.drop_table('volcanic_events')
    # Restore the pre-volcanic CHECK constraints exactly as b7c1a2d3e4f5 left them.
    for table, name, column in [
        ("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"),
        ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, _PRIOR_HAZARD_VALUES)}) NOT VALID"
        )
