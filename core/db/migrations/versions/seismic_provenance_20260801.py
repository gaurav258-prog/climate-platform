"""Relabel historical seismic hazard rows to distinguish the ESHM20 zone approximation from the raster (audit T13).

Both the real ESHM20 GeoTIFF path and the coarse zone-approximation fallback previously wrote
source_provider='eshm20_pga', so an auditor could not tell a genuine model raster value from our
hand-drawn zone table. No GeoTIFF has ever been ingested (none exists in the repo), so every existing
'eshm20_pga' row is in fact the zone approximation — relabel it honestly. Going forward the adapter
tags the two paths distinctly at ingest time.

Revision ID: seismic_provenance_20260801
Revises: config_policy_actions_20260731
"""
from alembic import op

revision = "seismic_provenance_20260801"
down_revision = "config_policy_actions_20260731"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only the old generic label (notes ending in "| ESHM20") is the untagged approximation.
    op.execute("""
        UPDATE satellite_observations
        SET    source_provider = 'eshm20_zone_approx',
               quality_flag = 1,
               quality_notes = replace(quality_notes, '| ESHM20',
                                       '| ESHM20 zone approximation (fallback, not the published raster)')
        WHERE  hazard_type = 'seismic'
          AND  source_provider = 'eshm20_pga'
          AND  quality_notes LIKE '%| ESHM20'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE satellite_observations
        SET    source_provider = 'eshm20_pga',
               quality_flag = 0,
               quality_notes = replace(quality_notes,
                                       '| ESHM20 zone approximation (fallback, not the published raster)',
                                       '| ESHM20')
        WHERE  hazard_type = 'seismic'
          AND  source_provider = 'eshm20_zone_approx'
    """)
