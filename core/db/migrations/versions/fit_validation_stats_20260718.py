"""Store the out-of-sample validation stats a fit needs for its Confidence Grade.

The in-sample r² flatters (it is measured on the years the line was fitted to). The Confidence
Grade keys on the HONEST numbers instead:
  r2_oos      — leave-one-out cross-validated r² (predict each year from a fit without it)
  band_cov68  — fraction of years inside the 1σ prediction interval (a calibrated band ~0.68)
Both are computed at fit time (ml/features/crop_fit) and stored so the grade is a pure function
of persisted, auditable fields.
"""
from alembic import op
import sqlalchemy as sa

revision = "fit_validation_stats_20260718"
down_revision = "soil_water_hazard_vocab_20260718"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sc_commodity_fit", sa.Column("r2_oos", sa.Numeric(6, 4)))
    op.add_column("sc_commodity_fit", sa.Column("band_cov68", sa.Numeric(5, 4)))


def downgrade():
    op.drop_column("sc_commodity_fit", "band_cov68")
    op.drop_column("sc_commodity_fit", "r2_oos")
