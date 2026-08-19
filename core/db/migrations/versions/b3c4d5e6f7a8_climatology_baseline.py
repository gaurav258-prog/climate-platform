"""climatology_baseline

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-04

Global 1991-2020 monthly climatology (mean+std per H3 cell per calendar month)
for 2m temperature and total precipitation — the baseline heat/drought on-demand
scoring compares "today's" ERA5-Land reading against, so any point on Earth can
be scored, not just the handful of regions already batch-processed. Sourced from
ECMWF's own pre-aggregated `reanalysis-era5-single-levels-monthly-means` (NOT
30 years of raw hourly/daily data fetched and aggregated ourselves — confirmed
live that ECMWF already computes and serves the monthly means directly, cutting
this from a multi-day raw-data engineering project down to a single ~1GB fetch).

Deliberately at ERA5's native 0.25 deg resolution (not H3 res 8 / ERA5-Land's
0.1 deg) -- climatology is a smooth quantity, and this project already has a
"nearest-neighbor fill" convention for exactly this kind of coarser-baseline-vs-
finer-query-cell mismatch (see flood/pollution/wildfire on-demand scorers).
h3_cell here is the h3 cell of each ERA5 grid POINT's centre, not an
independently-modelled value for every res-8 cell in between.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'climatology_baseline',
        sa.Column('h3_cell', sa.String(20), nullable=False),
        sa.Column('month', sa.SmallInteger(), nullable=False),  # 1-12
        sa.Column('temp_mean_k', sa.Numeric(7, 3), nullable=True),
        sa.Column('temp_std_k', sa.Numeric(7, 3), nullable=True),
        sa.Column('precip_mean_mm', sa.Numeric(9, 3), nullable=True),
        sa.Column('precip_std_mm', sa.Numeric(9, 3), nullable=True),
        sa.Column('baseline_period', sa.String(20), nullable=False, server_default='1991-2020'),
        sa.Column('lat', sa.Numeric(8, 5), nullable=False),
        sa.Column('lon', sa.Numeric(8, 5), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('h3_cell', 'month'),
    )
    op.create_index('idx_climatology_baseline_cell', 'climatology_baseline', ['h3_cell'], postgresql_using='btree')


def downgrade() -> None:
    op.drop_table('climatology_baseline')
