"""WS4d — coastal exposure per cell (elevation + distance to coast) for sea-level-rise risk.

Sea-level rise only threatens LOW-lying assets NEAR the coast — an inland or high-elevation asset
has zero SLR exposure. So the SLR/coastal-flood hazard needs two inputs the platform never had:
each cell's elevation above sea level and its distance to the coastline. This table holds them,
populated by scripts/build_coastal_exposure.py (Open-Meteo elevation + Natural Earth coastline).

Revision ID: coastal_exposure_202608
Revises: fin_proj_ci_202608
"""
from alembic import op

revision = "coastal_exposure_202608"
down_revision = "fin_proj_ci_202608"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE coastal_exposure (
        h3_cell          varchar PRIMARY KEY,
        latitude         double precision,
        longitude        double precision,
        elevation_m      double precision,   -- metres above mean sea level (DEM; NULL if unknown)
        dist_to_coast_km double precision,   -- great-circle distance to nearest coastline
        is_coastal       boolean,            -- within the coastal exposure band (dist <= threshold)
        source           varchar,
        fetched_at       timestamptz
    );
    """)
    # admit the new coastal_flood hazard into the canonical_scores hazard vocabulary
    op.execute("ALTER TABLE canonical_scores DROP CONSTRAINT IF EXISTS ck_canonical_hazard_vocab;")
    op.execute("""
        ALTER TABLE canonical_scores ADD CONSTRAINT ck_canonical_hazard_vocab
        CHECK (hazard_type IN ('flood','coastal_flood','heat_acute','heat_chronic','wildfire','drought',
                               'storm','seismic','volcanic','pollution','frost','soil_water')) NOT VALID;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE canonical_scores DROP CONSTRAINT IF EXISTS ck_canonical_hazard_vocab;")
    op.execute("""
        ALTER TABLE canonical_scores ADD CONSTRAINT ck_canonical_hazard_vocab
        CHECK (hazard_type IN ('flood','heat_acute','heat_chronic','wildfire','drought',
                               'storm','seismic','volcanic','pollution','frost','soil_water')) NOT VALID;
    """)
    op.execute("DROP TABLE IF EXISTS coastal_exposure;")
