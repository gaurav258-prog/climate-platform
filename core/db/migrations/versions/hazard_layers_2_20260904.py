"""hazard_layers_2 — the long-tail EU-Taxonomy hazards

(1) Extend the hazard_type CHECK constraints to the vocabulary frozen below — now including
    saline_intrusion, glacial_lake_outburst, ocean_acidification, avalanche, solifluction, soil_degradation,
    severe_convective (same drop-and-re-add pattern). NOT VALID.
(2) terrain_cell — on-demand DEM slope cache (h3 cell → slope_deg, elevation_m), shared by the slope-driven
    hazards (avalanche, solifluction); built by ml/scoring/terrain.slope_degrees.
(3) glacial_lake_cell — preprocessed H3 exposure zone for glacial-lake outburst floods, from the GIGLak global
    glacial-lake inventory (scripts/ingest_glacial_lakes.py): per H3 cell within a size-scaled buffer of a
    glacial lake, the influencing lake's area / elevation / distance.
"""
from typing import Sequence, Union

from alembic import op

# Frozen vocabulary (self-contained migration — never import app code): core.types.HAZARD_VALUES as of commit 5628d63.
_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'coastal_flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic',
    'volcanic', 'pollution', 'frost', 'soil_water', 'heavy_precip', 'landslide', 'temp_variability',
    'precip_variability', 'changing_temp', 'changing_precip', 'changing_wind', 'subsidence', 'permafrost',
    'soil_erosion', 'coastal_erosion', 'saline_intrusion', 'glacial_lake_outburst', 'ocean_acidification',
    'avalanche', 'solifluction', 'soil_degradation', 'severe_convective',
)

# The vocabulary in force at down_revision (hazard_layers_20260904) — what downgrade() restores.
_PRIOR_HAZARD_VALUES: tuple[str, ...] = (
    'flood', 'coastal_flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic',
    'volcanic', 'pollution', 'frost', 'soil_water', 'heavy_precip', 'landslide', 'temp_variability',
    'precip_variability', 'changing_temp', 'changing_precip', 'changing_wind', 'subsidence', 'permafrost',
    'soil_erosion', 'coastal_erosion',
)

revision: str = "hazard_layers_2_20260904"
down_revision: Union[str, None] = "hazard_layers_20260904"
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

    op.execute("""
        CREATE TABLE IF NOT EXISTS terrain_cell (
            h3_cell     TEXT NOT NULL PRIMARY KEY,
            slope_deg   REAL NOT NULL,
            elevation_m REAL NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS glacial_lake_cell (
            h3_cell        TEXT NOT NULL PRIMARY KEY,
            lake_area_km2  REAL NOT NULL,
            lake_elev_m    REAL,
            dist_km        REAL NOT NULL,
            data_vintage   TEXT
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS glacial_lake_cell")
    op.execute("DROP TABLE IF EXISTS terrain_cell")
    # Restore the pre-hazard_layers_2 CHECK constraints exactly as hazard_layers_20260904 left them.
    for table, name, column in [
        ("canonical_scores", "ck_canonical_hazard_vocab", "hazard_type"),
        ("satellite_observations", "ck_obs_hazard_vocab", "hazard_type"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, _PRIOR_HAZARD_VALUES)}) NOT VALID"
        )
