"""Per-plot irrigation status — an honest water-management CONTEXT flag (not a fabricated € modifier).

The engine models the physical water balance (drought/SPEI + soil_water) but not human water MANAGEMENT.
The project's reservoir null-result showed a FITTED irrigation buffer can't clear the r²≥0.40 publish
floor, and no global irrigation dataset is on hand — so irrigation is captured as customer-declared plot
metadata and SURFACED as context ("an irrigated plot's drought score is an upper bound"), never used to
silently adjust the published euro (which already reflects the origin's national irrigated/rain-fed mix).

Revision ID: plot_irrigation_202608
Revises: frostbase_latlon_202608
"""
from alembic import op

revision = "plot_irrigation_202608"
down_revision = "frostbase_latlon_202608"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sc_sourcing_plots ADD COLUMN IF NOT EXISTS irrigation_status VARCHAR(16)")
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_plot_irrigation') THEN
                ALTER TABLE sc_sourcing_plots ADD CONSTRAINT ck_plot_irrigation
                    CHECK (irrigation_status IS NULL OR irrigation_status IN ('irrigated','rain_fed','mixed'));
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE sc_sourcing_plots DROP CONSTRAINT IF EXISTS ck_plot_irrigation")
    op.execute("ALTER TABLE sc_sourcing_plots DROP COLUMN IF EXISTS irrigation_status")
