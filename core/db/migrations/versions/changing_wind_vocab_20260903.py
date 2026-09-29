"""changing_wind_hazard_vocab

Adds 'changing_wind' to HazardType (core/types.py) and extends the hazard_type CHECK constraints — same
pattern as heavy_precip_vocab_20260831 / frost / pollution: drop and re-add each constraint from the
vocabulary frozen below (now including CHANGING_WIND). NOT VALID so existing rows aren't re-scanned.

Changing wind patterns is the EU-Taxonomy wind-family chronic hazard (Appendix A). It is a Screening-tier
projection channel scored from the CMIP6 ensemble |fractional near-surface wind-speed change| (sfcWind) vs the
1995–2014 baseline — see ml/scoring/climate_change_point.py (score_changing_wind_point) and the wind delta
field built by scripts/build_cmip6_wind.py. This moves changing_wind from ROADMAP → live in the hazard
taxonomy (core/hazard_taxonomy.py), taking EU-Taxonomy coverage to 17/28 live.
"""
from typing import Sequence, Union

from alembic import op

# Frozen vocabulary (self-contained migration — never import app code): core.types.HAZARD_VALUES as of
# commit aeea078's parent plus 'changing_wind' (aeea078 also added hazard_layers_20260904, which adds the
# next four). landslide..changing_precip had entered core.types after 87e6bea without their own migration.
_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'coastal_flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic',
    'volcanic', 'pollution', 'frost', 'soil_water', 'heavy_precip', 'landslide', 'temp_variability',
    'precip_variability', 'changing_temp', 'changing_precip', 'changing_wind',
)

# The vocabulary in force at down_revision (heavy_precip_vocab_20260831) — what downgrade() restores.
_PRIOR_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'coastal_flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic',
    'volcanic', 'pollution', 'frost', 'soil_water', 'heavy_precip',
)

revision: str = "changing_wind_vocab_20260903"
down_revision: Union[str, None] = "coastal_subsidence_20260903"
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
    # Restore the pre-changing_wind CHECK constraints exactly as heavy_precip_vocab_20260831 left them.
    for table, name, column in [
        ("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"),
        ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, _PRIOR_HAZARD_VALUES)}) NOT VALID"
        )
