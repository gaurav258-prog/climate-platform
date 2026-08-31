"""heavy_precip_hazard_vocab

Adds 'heavy_precip' to HazardType (core/types.py) and extends the hazard_type CHECK constraints — same
pattern as d5e6f7a8b9c0 (frost) and a2b3c4d5e6f7 (pollution): drop and re-add each constraint from the
current core.types.HAZARD_VALUES (now including HEAVY_PRECIP). NOT VALID so existing rows aren't re-scanned.

Heavy precipitation is the first EU-Taxonomy Phase-1 channel (docs/board/path_to_28.html) — a Screening-tier
extreme-rainfall indicator scored from the wettest-month precipitation climatology (climatology_baseline),
see ml/scoring/heavy_precip_point.py.

NOTE: this branches off validation_framework_20260828; the DB-source-of-truth branch adds
orm_reconcile_20260831 off the same parent, so a heads-merge migration will be needed when both land.
"""
from typing import Sequence, Union

from alembic import op

from core.types import HAZARD_VALUES

revision: str = "heavy_precip_vocab_20260831"
down_revision: Union[str, None] = "validation_framework_20260828"
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
    # Does not restore the pre-heavy_precip CHECK (would need the prior HAZARD_VALUES snapshot).
    pass
