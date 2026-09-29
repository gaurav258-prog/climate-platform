"""windstorm_vocab — add the extratropical-windstorm hazard to the vocabulary CHECK constraints.

EU-Taxonomy Appendix A separates 'Storm (blizzard, dust, sand)' from 'Cyclone/hurricane/typhoon'. The new
HazardType.WINDSTORM (ERA5 gust-climatology channel, distinct from the tropical-cyclone STORM channel) adds
'windstorm' to core.types.HAZARD_VALUES; this rebuilds the hazard_type CHECK constraints from that list (frozen below), same
drop-and-re-add pattern as the prior vocab migrations. NOT VALID (new rows enforced;
existing rows untouched).
"""
from typing import Sequence, Union

from alembic import op

# Frozen vocabulary (self-contained migration — never import app code): core.types.HAZARD_VALUES as of commit 090e8f2.
_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'coastal_flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'windstorm',
    'seismic', 'volcanic', 'pollution', 'frost', 'soil_water', 'heavy_precip', 'landslide',
    'temp_variability', 'precip_variability', 'changing_temp', 'changing_precip', 'changing_wind',
    'subsidence', 'permafrost', 'soil_erosion', 'coastal_erosion', 'saline_intrusion',
    'glacial_lake_outburst', 'ocean_acidification', 'avalanche', 'solifluction', 'soil_degradation',
    'severe_convective',
)

# The vocabulary in force at down_revision (hazard_layers_2_20260904) — what downgrade() restores.
_PRIOR_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'coastal_flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic',
    'volcanic', 'pollution', 'frost', 'soil_water', 'heavy_precip', 'landslide', 'temp_variability',
    'precip_variability', 'changing_temp', 'changing_precip', 'changing_wind', 'subsidence', 'permafrost',
    'soil_erosion', 'coastal_erosion', 'saline_intrusion', 'glacial_lake_outburst', 'ocean_acidification',
    'avalanche', 'solifluction', 'soil_degradation', 'severe_convective',
)

revision: str = "windstorm_vocab_20260905"
down_revision: Union[str, None] = "hazard_layers_2_20260904"
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
    # Restore the pre-windstorm CHECK constraints exactly as hazard_layers_2_20260904 left them.
    for table, name, column in [
        ("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"),
        ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, _PRIOR_HAZARD_VALUES)}) NOT VALID"
        )
