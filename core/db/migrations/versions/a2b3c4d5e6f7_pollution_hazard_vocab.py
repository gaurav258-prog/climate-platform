"""pollution_hazard_vocab

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-03

Adds 'pollution' to HazardType (core/types.py) and extends the hazard_type CHECK
constraints (same pattern as d3e4f5a6b7c8's volcanic addition) — drop and re-add
from the current core.types.HAZARD_VALUES (now includes POLLUTION).

Pollution is a categorically different kind of risk from every other hazard here:
it measures chronic health exposure to PEOPLE, not structural/crop damage, so it's
kept as its own hazard_type rather than blended into an existing one — same
"don't collapse mechanistically different channels" convention as agriculture's
Market vs Sourcing split.
"""
from typing import Sequence, Union

from alembic import op

from core.types import HAZARD_VALUES

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
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
    # Note: does not restore the pre-pollution CHECK constraint (would need the
    # prior HAZARD_VALUES snapshot); re-run d3e4f5a6b7c8's logic manually if needed.
    pass
