"""hazard_layers_2 — the long-tail EU-Taxonomy hazards

(1) Extend the hazard_type CHECK constraints to the current core.types.HAZARD_VALUES — now including
    saline_intrusion, glacial_lake_outburst, ocean_acidification, avalanche, solifluction, soil_degradation,
    severe_convective (same drop-and-re-add-from-HAZARD_VALUES pattern). NOT VALID.
(2) terrain_cell — on-demand DEM slope cache (h3 cell → slope_deg, elevation_m), shared by the slope-driven
    hazards (avalanche, solifluction); built by ml/scoring/terrain.slope_degrees.
(3) glacial_lake_cell — preprocessed H3 exposure zone for glacial-lake outburst floods, from the GIGLak global
    glacial-lake inventory (scripts/ingest_glacial_lakes.py): per H3 cell within a size-scaled buffer of a
    glacial lake, the influencing lake's area / elevation / distance.
"""
from typing import Sequence, Union

from alembic import op

from core.types import HAZARD_VALUES

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
            f"ADD CONSTRAINT {name} CHECK ({_in_list(column, HAZARD_VALUES)}) NOT VALID"
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
    # Does not restore the pre-hazard_layers_2 CHECK (would need the prior HAZARD_VALUES snapshot).
