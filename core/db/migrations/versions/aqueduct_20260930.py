"""WRI Aqueduct 4.0 baseline water risk by basin — the dataset ESRS names for areas of (high) water stress.

aqueduct_loads    every load of the dataset kept (version, vintage, the file's sha256), the current one open
aqueduct_basins   one row per Aqueduct unit (HydroBASINS level 6 × GADM level 1): baseline water stress and baseline
                  water depletion (raw ratio, category, label as WRI codes them) and the boundary (WKB) with its
                  bounding box, so a site is placed by an exact point-in-polygon test on the few basins whose box holds
                  it (no PostGIS at runtime — services/reference/aqueduct.py)

Revision ID: aqueduct_20260930
Revises: csrd_role_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "aqueduct_20260930"
down_revision: Union[str, None] = "csrd_role_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO aqueduct_loads (load_id, version, source) VALUES ('0bbe0bbe-0000-4000-8000-00000000feeb', 'probe', 'probe');""",
    "cleanup": """DELETE FROM aqueduct_loads WHERE load_id = '0bbe0bbe-0000-4000-8000-00000000feeb';""",
}


def upgrade() -> None:
    op.execute("""
        CREATE TABLE aqueduct_loads (
            load_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            version      TEXT NOT NULL,
            data_vintage DATE,
            source       TEXT NOT NULL,
            sha256       TEXT,
            n_basins     INTEGER,
            loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            retired_at   TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX ux_aqueduct_load_current ON aqueduct_loads ((true)) WHERE retired_at IS NULL;
        CREATE TABLE aqueduct_basins (
            load_id    UUID NOT NULL REFERENCES aqueduct_loads(load_id) ON DELETE CASCADE,
            string_id  TEXT NOT NULL,
            pfaf_id    BIGINT,
            gid_1      TEXT,
            name_0     TEXT,
            name_1     TEXT,
            bws_raw    DOUBLE PRECISION,
            bws_cat    SMALLINT,
            bws_label  TEXT,
            bwd_raw    DOUBLE PRECISION,
            bwd_cat    SMALLINT,
            bwd_label  TEXT,
            minx DOUBLE PRECISION NOT NULL, miny DOUBLE PRECISION NOT NULL,
            maxx DOUBLE PRECISION NOT NULL, maxy DOUBLE PRECISION NOT NULL,
            geom_wkb   BYTEA NOT NULL,
            PRIMARY KEY (load_id, string_id)
        );
        CREATE INDEX ix_aqueduct_bbox ON aqueduct_basins (load_id, minx, maxx, miny, maxy);
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM aqueduct_loads) THEN
                RAISE EXCEPTION 'cannot downgrade aqueduct_20260930: an Aqueduct load is recorded (filings may have read it)';
            END IF;
        END $$;
    """)
    op.execute("DROP TABLE aqueduct_basins; DROP TABLE aqueduct_loads;")
