"""frost_hazard_vocab

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-09

Adds 'frost' to HazardType (core/types.py) and extends the hazard_type CHECK
constraints (same pattern as a2b3c4d5e6f7's pollution addition) -- drop and
re-add from the current core.types.HAZARD_VALUES (now includes FROST).

Frost is coffee's second real 2021 driver (the first, drought, was already
scored) -- see ml/features/frost.py and scripts/wire_frost_demo.py. It was
blocked until now because CDS's own daily-minimum-temperature statistic is
ECMWF-flagged unusable; the fix computes the daily/seasonal minimum locally
from raw hourly ERA5 instead of trusting that flagged derived product.
"""
from typing import Sequence, Union

from alembic import op

from core.types import HAZARD_VALUES

revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _in_list(column: str, values) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    for table, name, column in [
        ("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"),
        ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, HAZARD_VALUES)}) NOT VALID"
        )


def downgrade() -> None:
    # Note: does not restore the pre-frost CHECK constraint (would need the
    # prior HAZARD_VALUES snapshot); re-run a2b3c4d5e6f7's logic manually if needed.
    pass
