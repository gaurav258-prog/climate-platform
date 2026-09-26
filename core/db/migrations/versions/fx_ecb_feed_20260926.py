"""FX rates as a live ECB feed: keep the rate exactly as the ECB publishes it, and when we fetched it.

  * fx_rates.units_per_eur — the ECB's published figure (foreign currency per 1 EUR, e.g. USD 1.1403), the value an
    auditor can check against the ECB file; eur_per_unit remains the derived figure conversions multiply by.
  * fx_rates.fetched_at — when this row was last written from the source.
Rows loaded at first setup carry source 'seed' and are overwritten by the ECB history on the first feed run.

Revision ID: fx_ecb_feed_20260926
Revises: job_runs_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "fx_ecb_feed_20260926"
down_revision: Union[str, None] = "job_runs_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE fx_rates ADD COLUMN IF NOT EXISTS units_per_eur NUMERIC(18, 6)")
    op.execute("ALTER TABLE fx_rates ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE fx_rates DROP COLUMN IF EXISTS fetched_at, DROP COLUMN IF EXISTS units_per_eur")
