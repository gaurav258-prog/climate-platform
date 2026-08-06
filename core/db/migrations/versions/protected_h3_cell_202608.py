"""Protected-area H3 lookup — the precomputed set of H3 cells that fall inside (or within a buffer of) a
Natura 2000 protected area. Built offline from the EEA Natura 2000 GeoPackage (no PostGIS needed at runtime):
an asset/plot's `h3_cell` is a simple indexed membership test. Feeds ESRS E4 (own sites + sourcing plots
in/near a protected area).

Revision ID: protected_h3_cell_202608
Revises: provided_datapoint_202608
"""
from alembic import op

revision = "protected_h3_cell_202608"
down_revision = "provided_datapoint_202608"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE IF NOT EXISTS protected_h3_cell (
    h3_cell     TEXT NOT NULL,
    h3_res      SMALLINT NOT NULL DEFAULT 8,
    dataset     TEXT NOT NULL DEFAULT 'natura2000',   -- source dataset (natura2000 · wdpa · …)
    within_km   DOUBLE PRECISION NOT NULL DEFAULT 0,   -- 0 = the cell overlaps a protected polygon; >0 = within this buffer
    site_ref    TEXT,                                  -- the protected-area site code (e.g. Natura 2000 SITECODE)
    data_vintage DATE,
    PRIMARY KEY (h3_cell, dataset)
);
CREATE INDEX IF NOT EXISTS ix_protected_h3_dataset ON protected_h3_cell(dataset);
"""

DOWN = "DROP TABLE IF EXISTS protected_h3_cell;"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
