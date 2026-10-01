"""supervision_geo_prior held each geography's share of scored land in the High / Very-high bands — one fixed reading
of 'sensitive'. A share is now compared at the at-risk level the entity stated for the template being judged (E69), so
the store keeps each region's headline scores (sorted, in hundredths) and hazards: supervision_geo_prior_region. The
share at any stated level is an exact count at read time. The old table is kept, renamed; the downgrade restores it.
The new table is filled by the worker (supervision.rebuild_geo_priors) or scripts.build_geo_priors.

Revision ID: geo_prior_levels_20260930
Revises: views_threshold_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "geo_prior_levels_20260930"
down_revision: Union[str, None] = "views_threshold_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE supervision_geo_prior RENAME TO supervision_geo_prior_retired_20260930;
        CREATE TABLE supervision_geo_prior_region (
            geography   TEXT NOT NULL,
            scenario    TEXT NOT NULL,
            horizon     TEXT NOT NULL,
            region      TEXT NOT NULL,
            scores      SMALLINT[] NOT NULL,
            hazards     TEXT[] NOT NULL,
            source_note TEXT,
            built_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (geography, scenario, horizon, region),
            CONSTRAINT ck_geo_prior_region_parallel CHECK (cardinality(scores) = cardinality(hazards) AND cardinality(scores) > 0)
        );
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE supervision_geo_prior_region;
        ALTER TABLE supervision_geo_prior_retired_20260930 RENAME TO supervision_geo_prior;
    """)
