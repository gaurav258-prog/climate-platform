"""Global root-zone soil-moisture climatology baseline — unlocks soil_water scoring anywhere (global build G1).

Mirror of climatology_baseline (temp/precip) for the soil-water driver: per H3 cell per calendar month, the
1991-2020 mean + std of the depth-weighted root-zone volumetric soil water (ERA5 layers 2+3). The soil_water
on-demand scorer standardises a live reading against this to get the anomaly z it needs — the same way the
temp/precip baseline unlocks drought/heat anywhere. Replaces the region-tiled .nc files (Iberia-only).

Revision ID: soil_moisture_baseline_202608
Revises: plot_geocode_quality_20260801
"""
import sqlalchemy as sa
from alembic import op

revision = "soil_moisture_baseline_202608"
down_revision = "plot_geocode_quality_20260801"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "soil_moisture_baseline",
        sa.Column("h3_cell", sa.String(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("sm_mean", sa.Float(), nullable=False),   # depth-weighted root-zone volumetric water (m3/m3)
        sa.Column("sm_std", sa.Float(), nullable=True),
        sa.Column("baseline_period", sa.String(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("h3_cell", "month"),
    )


def downgrade() -> None:
    op.drop_table("soil_moisture_baseline")
