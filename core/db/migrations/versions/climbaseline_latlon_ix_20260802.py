"""Index climatology_baseline on (lat, lon) — the missing index behind slow on-demand heat scoring.

climatology_baseline holds 12.3M rows (30-yr monthly global temperature normals). The chronic-heat
point scorer (ml/features/heat_chronic_point.py) finds the nearest grid point with a bounded-box
`lat BETWEEN … AND lon BETWEEN …` query. With only the primary key and the H3-cell index present, that
box was a full parallel sequential scan — ~34s PER on-demand lookup. This made the H3 granular-grid ring
(and every any-address heat lookup) crawl. A composite btree on (lat, lon) turns it into a millisecond
range scan.

Revision ID: climbaseline_latlon_202608
Revises: approval_returned_202608
"""
from alembic import op

revision = "climbaseline_latlon_202608"
down_revision = "approval_returned_202608"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE INDEX IF NOT EXISTS idx_climatology_baseline_latlon "
               "ON climatology_baseline (lat, lon)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_climatology_baseline_latlon")
