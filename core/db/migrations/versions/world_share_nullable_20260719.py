"""Make sc_commodity_calibration.world_share NULLABLE.

The column was declared NOT NULL by the original per-origin seed (sc_calibration_20260715),
when every calibration row was a curated world-share origin. The later ranged-tier design
(ranged_tier_20260718) introduced calibration rows created BY A FIT for a tested origin that
is NOT part of any curated world-production share — a rain-fed validation origin (e.g. Algeria
/ Tunisia wheat) whose world_share is legitimately unknown and intentionally left NULL. The
fit-persist path in scripts/fit_ranged_crop.py documents this ("world_share is left NULL"),
but the stale NOT NULL constraint rejected the INSERT, so the INSERT branch had never actually
run (all prior crops had pre-seeded rows and took the UPDATE branch).

Read-path consumers already treat world_share as optional: services/intelligence/supply_cogs.py
sums only non-NULL shares (`sum(... if o["world_share"] is not None)`), and the world-shock
roll-up is withheld for a held crop regardless. So NULL is the correct, already-handled value
for a tested origin with no curated share. Drop the NOT NULL.

Revision ID: world_share_nullable_20260719
Revises: fit_validation_stats_20260718
"""
from alembic import op

revision = "world_share_nullable_20260719"
down_revision = "fit_validation_stats_20260718"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("sc_commodity_calibration", "world_share", nullable=True)


def downgrade() -> None:
    # Restore the constraint; any NULLs introduced meanwhile would block this (as intended —
    # a tested origin with no curated share should not be forced to a fake number).
    op.alter_column("sc_commodity_calibration", "world_share", nullable=False)
