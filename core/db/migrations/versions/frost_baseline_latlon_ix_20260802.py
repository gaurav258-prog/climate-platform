"""Index the global frost + soil-moisture baselines by (lat, lon) for on-demand point scoring.

frost_baseline (3.1M rows) and soil_moisture_baseline (12.3M rows) each only had a PK on
(h3_cell, month). Their on-demand point scorers find the nearest baseline cell to an arbitrary uploaded
point via a small lat/lon bounding box — without this index that is a full seq scan on every new-plot
lookup (measured: soil_water 2.7s → the exact issue the climatology_baseline index fixed for chronic
heat). This makes frost AND root-zone water stress scoreable at any address at interactive speed.

Revision ID: frostbase_latlon_202608
Revises: sc_challenger_202608
"""
from alembic import op

revision = "frostbase_latlon_202608"
down_revision = "sc_challenger_202608"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_frost_baseline_latlon ON frost_baseline (lat, lon)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_soil_moisture_baseline_latlon ON soil_moisture_baseline (lat, lon)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_frost_baseline_latlon")
    op.execute("DROP INDEX IF EXISTS idx_soil_moisture_baseline_latlon")
