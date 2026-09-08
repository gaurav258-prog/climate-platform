"""supervision_geo_prior — what the platform's own hazard layers imply for a geography, without any entity rows.

Built by scripts/build_geo_priors.py from the standing canonical scores: per geography (country, or EU) and basis,
the share of scored land cells whose headline hazard is High/Very high, and the spread of that share across the
geography's regions (NUTS-3 in the EU, H3 res-4 elsewhere). The Tier-1 plausibility band reads it.

Revision ID: sup_geo_prior_20260908
Revises: sup_scope_ack_20260908
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_geo_prior_20260908"
down_revision: Union[str, None] = "sup_scope_ack_20260908"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervision_geo_prior (
            geography        TEXT NOT NULL,
            scenario         TEXT NOT NULL,
            horizon          TEXT NOT NULL,
            n_cells          INTEGER NOT NULL,
            share_sensitive  DOUBLE PRECISION NOT NULL,   -- share of scored cells with headline High/Very high
            p10              DOUBLE PRECISION,            -- spread of that share across the geography's regions
            p25              DOUBLE PRECISION,
            p50              DOUBLE PRECISION,
            p75              DOUBLE PRECISION,
            p90              DOUBLE PRECISION,
            n_regions        INTEGER NOT NULL DEFAULT 0,
            hazard_mix       JSONB,                       -- headline hazards behind the sensitive cells
            source_note      TEXT,
            built_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (geography, scenario, horizon)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervision_geo_prior")
