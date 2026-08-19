"""crop_yield_ground_truth

The labels the agriculture AI layer needs and the platform never had: observed crop
production / yield by commodity × country × season. This is the ground truth the
hazard → yield impact function is calibrated and BACKTESTED against (e.g. reproduce
the cocoa 2023/24 −12.9% world production shock). Sources: FAOSTAT (QCL), ICCO (cocoa),
ICO (coffee). Append-only-ish; UNIQUE on (commodity, country, season_year, source) so a
re-ingest updates rather than duplicates.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPGRADE = """
CREATE TABLE IF NOT EXISTS crop_yield_observations (
    obs_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    commodity         VARCHAR(80)  NOT NULL,   -- cocoa, coffee_arabica, coffee_robusta, ...
    country           VARCHAR(3),              -- ISO-2 (CI, GH, BR) or WLD for world
    region            VARCHAR(120),            -- optional sub-national origin
    season_year       INT NOT NULL,            -- crop-year END (2024 = 2023/24 season)
    production_tonnes NUMERIC(16,1),
    area_harvested_ha NUMERIC(16,1),
    yield_tonnes_ha   NUMERIC(12,4),
    yoy_change_pct    NUMERIC(8,2),            -- derived on ingest (vs prior season, same key)
    source            VARCHAR(200) NOT NULL,   -- 'ICCO Nov-2025 bulletin', 'FAOSTAT QCL', ...
    note              TEXT,
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (commodity, country, season_year, source)
);
CREATE INDEX IF NOT EXISTS ix_crop_yield_commodity ON crop_yield_observations (commodity, season_year);
CREATE INDEX IF NOT EXISTS ix_crop_yield_country   ON crop_yield_observations (country, commodity);
"""

DOWNGRADE = "DROP TABLE IF EXISTS crop_yield_observations;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
