"""cold_wave — a building-relevant extreme-cold channel joins the hazard vocabulary (CHECK constraints re-derived
from core.types.HAZARD_VALUES, the same pattern as hazard_layers_2).

Revision ID: cold_wave_20260910
Revises: scores_current_index_20260909
"""
from typing import Sequence, Union

from alembic import op

from core.types import HAZARD_VALUES

revision: str = "cold_wave_20260910"
down_revision: Union[str, None] = "scores_current_index_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _in_list(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    for table, name, column in [("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"), ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type")]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({_in_list(column, HAZARD_VALUES)}) NOT VALID")


def downgrade() -> None:
    pass   # the vocabulary only grows; the constraint is re-derived by the next migration that touches it
