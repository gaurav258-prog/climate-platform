"""Add per-cell land-subsidence rate to coastal_exposure — the vertical-land-motion term of relative SLR.

Effective coastal exposure is RELATIVE sea-level rise = sea-level rise + local land subsidence. This column
holds the subsidence rate (mm/yr, positive = sinking) so the freeboard screen can subtract accumulated land
motion to the horizon. NULL until an InSAR feed (Copernicus EGMS for EU coasts, or a global VLM product)
populates it — the model is subsidence-aware, the data ingest is the disclosed follow-on. See
ml/scoring/sea_level.py (v2) and ml/scoring/model_limitations.py (land_subsidence).

Revision ID: coastal_subsidence_20260903
Revises: fcf53e319275
"""
from alembic import op

revision = "coastal_subsidence_20260903"
down_revision = "fcf53e319275"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE coastal_exposure ADD COLUMN IF NOT EXISTS subsidence_mm_yr double precision")


def downgrade() -> None:
    op.execute("ALTER TABLE coastal_exposure DROP COLUMN IF EXISTS subsidence_mm_yr")
