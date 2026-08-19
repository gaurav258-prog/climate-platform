"""vocabulary_constraints

Enforce the canonical vocabulary at the database level. Until now hazard_type /
scenario were free VARCHARs, so the NGFS-vs-IPCC and heat-vs-heat_acute drift
could be written straight into the golden source. These CHECK constraints reject
any value not in core.types, so the DB and the Python enums can never disagree.

The allowed-value lists are imported from core.types — they are NOT hand-copied
here, so there is exactly one source of truth.

Revision ID: b7c1a2d3e4f5
Revises: a1b2c3d4e5f6
Create Date: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op

from core.types import HAZARD_VALUES, SCENARIO_VALUES, TIME_HORIZON_VALUES

revision: str = "b7c1a2d3e4f5"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _in_list(column: str, values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


# (table, constraint_name, column, allowed_values)
_CONSTRAINTS = [
    ("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type", HAZARD_VALUES),
    ("canonical_scores", "ck_canonical_scenario_vocab", "scenario", SCENARIO_VALUES),
    ("canonical_scores", "ck_canonical_horizon_vocab", "time_horizon", TIME_HORIZON_VALUES),
    ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type", HAZARD_VALUES),
]


def upgrade() -> None:
    for table, name, column, values in _CONSTRAINTS:
        # NOT VALID: enforce on new/updated rows immediately without a full-table
        # scan; existing rows can be reconciled then VALIDATE CONSTRAINT run.
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, values)}) NOT VALID"
        )


def downgrade() -> None:
    for table, name, _column, _values in _CONSTRAINTS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
