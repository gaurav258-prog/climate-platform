"""Add sc_sourcing_plots.plot_geometry (GeoJSON) — the EUDR polygon boundary.

Phase 0 of the EUDR/CSRD build. Until now a plot was a POINT (latitude/longitude) plus an
optional plot_area_ha number. EUDR requires the actual PLOT BOUNDARY (a polygon) for every
plot above 4 ha; a point is permitted only at or below 4 ha. We store the boundary as a
GeoJSON geometry in a jsonb column rather than a PostGIS type on purpose: PostGIS is not
installed on the target server (`pg_available_extensions` has no 'postgis'), so binding the
schema to it would make the platform undeployable here. The geometry math (geodesic area,
point-in-polygon, forest-loss overlay) runs in Python via shapely/pyproj, which is portable
and unit-testable; a PostGIS geometry column can be added later purely as a query optimisation
without changing the source of truth. latitude/longitude stay as the plot CENTROID (the H3 key),
derived from the polygon when one is supplied.

Revision ID: plot_geometry_20260727
Revises: cocoa_claim_reconcile_20260719
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "plot_geometry_20260727"
down_revision = "cocoa_claim_reconcile_20260719"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: a point-only plot (≤4 ha, or a legacy row) has no polygon and stays NULL.
    op.add_column("sc_sourcing_plots", sa.Column("plot_geometry", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("sc_sourcing_plots", "plot_geometry")
