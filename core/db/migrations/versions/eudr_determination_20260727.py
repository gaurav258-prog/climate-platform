"""Add the COMPUTED EUDR determination columns to sc_sourcing_plots.

Phase 1 of the EUDR build. `eudr_status` stays as the customer's SELF-DECLARED value; these new
columns hold the determination WE compute from satellite forest data (services/intelligence/
eudr.py + forest.py) — the honest, independent answer. Keeping both lets the product show
"you declared X; our check says Y", which is the whole point of the deforestation engine.

Revision ID: eudr_determination_20260727
Revises: plot_geometry_20260727
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "eudr_determination_20260727"
down_revision = "plot_geometry_20260727"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sc_sourcing_plots", sa.Column("eudr_determination", sa.String(), nullable=True))
    op.add_column("sc_sourcing_plots", sa.Column("eudr_loss_ha", sa.Numeric(), nullable=True))
    op.add_column("sc_sourcing_plots", sa.Column("eudr_first_loss_year", sa.Integer(), nullable=True))
    op.add_column("sc_sourcing_plots", sa.Column("eudr_forest_source", sa.String(), nullable=True))
    op.add_column("sc_sourcing_plots", sa.Column("eudr_determined_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sc_sourcing_plots", sa.Column("eudr_evidence", JSONB, nullable=True))


def downgrade() -> None:
    for c in ("eudr_evidence", "eudr_determined_at", "eudr_forest_source",
              "eudr_first_loss_year", "eudr_loss_ha", "eudr_determination"):
        op.drop_column("sc_sourcing_plots", c)
