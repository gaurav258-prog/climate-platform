"""heavy_precip_hazard_vocab

Adds 'heavy_precip' to HazardType (core/types.py) and extends the hazard_type CHECK constraints — same
pattern as d5e6f7a8b9c0 (frost) and a2b3c4d5e6f7 (pollution): drop and re-add each constraint from the
vocabulary frozen below (now including HEAVY_PRECIP). NOT VALID so existing rows aren't re-scanned.

Heavy precipitation is the first EU-Taxonomy Phase-1 channel (docs/board/path_to_28.html) — a Screening-tier
extreme-rainfall indicator scored from the wettest-month precipitation climatology (climatology_baseline),
see ml/scoring/heavy_precip_point.py.

NOTE: this branches off validation_framework_20260828; the DB-source-of-truth branch adds
orm_reconcile_20260831 off the same parent, so a heads-merge migration will be needed when both land.
"""
from typing import Sequence, Union

from alembic import op

# Frozen vocabulary (self-contained migration — never import app code): core.types.HAZARD_VALUES as of commit 87e6bea.
_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'coastal_flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic',
    'volcanic', 'pollution', 'frost', 'soil_water', 'heavy_precip',
)

# In force at down_revision on canonical_scores — coastal_exposure_202608 added 'coastal_flood' there only.
_PRIOR_CANONICAL_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'coastal_flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic',
    'volcanic', 'pollution', 'frost', 'soil_water',
)

# In force at down_revision on satellite_observations — last rebuilt by soil_water_hazard_vocab_20260718.
_PRIOR_OBS_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic', 'volcanic',
    'pollution', 'frost', 'soil_water',
)

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
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, _HAZARD_VALUES)}) NOT VALID"
        )


def downgrade() -> None:
    # Restore the pre-heavy_precip CHECK constraints exactly — the two tables differed at down_revision.
    for table, name, column, values in [
        ("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type", _PRIOR_CANONICAL_HAZARD_VALUES),
        ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type", _PRIOR_OBS_HAZARD_VALUES),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, values)}) NOT VALID"
        )
