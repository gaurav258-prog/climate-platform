"""cold_wave — a building-relevant extreme-cold channel joins the hazard vocabulary (CHECK constraints rebuilt
from the vocabulary frozen below, the same pattern as hazard_layers_2).

Revision ID: cold_wave_20260910
Revises: scores_current_index_20260909
"""
from typing import Sequence, Union

from alembic import op

# Frozen vocabulary (self-contained migration — never import app code): core.types.HAZARD_VALUES as of commit ec0a91f (matches the live DB constraint).
_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'coastal_flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'windstorm',
    'seismic', 'volcanic', 'pollution', 'frost', 'cold_wave', 'soil_water', 'heavy_precip', 'landslide',
    'temp_variability', 'precip_variability', 'changing_temp', 'changing_precip', 'changing_wind',
    'subsidence', 'permafrost', 'soil_erosion', 'coastal_erosion', 'saline_intrusion',
    'glacial_lake_outburst', 'ocean_acidification', 'avalanche', 'solifluction', 'soil_degradation',
    'severe_convective',
)

# The vocabulary in force at down_revision (windstorm_vocab_20260905) — what downgrade() restores.
_PRIOR_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'coastal_flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'windstorm',
    'seismic', 'volcanic', 'pollution', 'frost', 'soil_water', 'heavy_precip', 'landslide',
    'temp_variability', 'precip_variability', 'changing_temp', 'changing_precip', 'changing_wind',
    'subsidence', 'permafrost', 'soil_erosion', 'coastal_erosion', 'saline_intrusion',
    'glacial_lake_outburst', 'ocean_acidification', 'avalanche', 'solifluction', 'soil_degradation',
    'severe_convective',
)

revision: str = "cold_wave_20260910"
down_revision: Union[str, None] = "scores_current_index_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _in_list(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    for table, name, column in [("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"), ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type")]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({_in_list(column, _HAZARD_VALUES)}) NOT VALID")


def downgrade() -> None:
    # Restore the pre-cold_wave CHECK constraints exactly as windstorm_vocab_20260905 left them.
    for table, name, column in [("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"), ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type")]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({_in_list(column, _PRIOR_HAZARD_VALUES)}) NOT VALID")
