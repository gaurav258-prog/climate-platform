"""Sourcing plots track geocode confidence + precision, at parity with sites (audit T4b).

sc_company_sites already stores `confidence` + `geocode_precision`; sc_sourcing_plots did not, so a
coarsely-geocoded plot carried no quality signal into the filing. Add the two columns (nullable — existing
rows are backfilled to the honest 'unknown' state, not a fabricated high confidence).

Revision ID: plot_geocode_quality_20260801
Revises: seismic_provenance_20260801
"""
import sqlalchemy as sa
from alembic import op

revision = "plot_geocode_quality_20260801"
down_revision = "seismic_provenance_20260801"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sc_sourcing_plots", sa.Column("confidence", sa.Numeric(), nullable=True))
    op.add_column("sc_sourcing_plots", sa.Column("geocode_precision", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("sc_sourcing_plots", "geocode_precision")
    op.drop_column("sc_sourcing_plots", "confidence")
