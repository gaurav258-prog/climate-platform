"""Global frost baseline — climatological coldest-night min-temp per cell/month (global build G2).

Frost is a daily extreme a mean-temperature baseline misses (the coffee backtest proved it). This baseline is
built from ERA5's actual DAILY-MINIMUM 2m temperature field (minimum_2m_temperature_since_previous_post_
processing), not from mean temperature: per H3 cell per calendar month, the climatological coldest-night
severity across 1991-2020 (mean daily-min and its inter-annual variability, so the scorer can take the
typical coldest night of the frost season). Replaces the Brazil-only region files so frost scores anywhere.

Revision ID: frost_baseline_202608
Revises: soil_moisture_baseline_202608
"""
from alembic import op
import sqlalchemy as sa

revision = "frost_baseline_202608"
down_revision = "soil_moisture_baseline_202608"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frost_baseline",
        sa.Column("h3_cell", sa.String(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("tmin_mean_c", sa.Float(), nullable=False),   # mean of daily-min 2m temp for this month (°C)
        sa.Column("tmin_std_c", sa.Float(), nullable=True),     # inter-annual std of the monthly-mean daily-min
        sa.Column("coldest_night_c", sa.Float(), nullable=False),  # climatological coldest-night estimate (°C)
        sa.Column("baseline_period", sa.String(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("h3_cell", "month"),
    )


def downgrade() -> None:
    op.drop_table("frost_baseline")
