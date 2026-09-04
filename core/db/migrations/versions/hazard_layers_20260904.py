"""hazard_layers — subsidence / permafrost / soil_erosion / coastal_erosion

Two things, one migration:
  (1) Extend the hazard_type CHECK constraints to the current core.types.HAZARD_VALUES — now including the four
      EU-Taxonomy solid-mass / erosion channels SUBSIDENCE, PERMAFROST, SOIL_EROSION, COASTAL_EROSION (same
      drop-and-re-add-from-HAZARD_VALUES pattern as changing_wind_vocab / heavy_precip_vocab). NOT VALID so
      existing rows aren't re-scanned.
  (2) Create coastal_erosion_cell — the preprocessed H3 lookup for the Vousdoukas et al. (2020, JRC LISCOAST)
      global shoreline-retreat projections: per H3 cell × RCP × year, the median (P50) long-term shoreline
      change in metres (negative = erosion / retreat). Built offline by scripts/ingest_coastal_erosion.py;
      read at runtime by ml/scoring/coastal_erosion_point.py (no PostGIS needed).

Moves subsidence + coastal_erosion from ROADMAP → live now (data in hand); permafrost + soil_erosion are
wired-ready (their rasters are fetched via scripts/fetch_permafrost.py / fetch_soil_erosion.py).
"""
from typing import Sequence, Union

from alembic import op

from core.types import HAZARD_VALUES

revision: str = "hazard_layers_20260904"
down_revision: Union[str, None] = "changing_wind_vocab_20260903"
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
        CREATE TABLE IF NOT EXISTS coastal_erosion_cell (
            h3_cell     TEXT    NOT NULL,
            rcp         TEXT    NOT NULL,          -- 'rcp45' | 'rcp85'
            year        INTEGER NOT NULL,          -- 2050 | 2100
            retreat_m   REAL    NOT NULL,          -- median (P50) long-term shoreline change, metres (neg = erosion)
            data_vintage TEXT,
            PRIMARY KEY (h3_cell, rcp, year)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS coastal_erosion_cell")
    # Does not restore the pre-hazard_layers CHECK (would need the prior HAZARD_VALUES snapshot).
