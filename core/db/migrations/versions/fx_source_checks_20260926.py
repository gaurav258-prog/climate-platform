"""How closely two FX sources agree, per currency — the evidence that a second source's series belongs to the currency
it is filed under, and how accurate a rate from it typically is.

  * fx_source_checks — per currency and pair of sources (e.g. IMF month-end vs ECB daily on the same day): number of
    comparisons, typical (median), 95th-percentile and worst gap in %, the verdict (accepted | refused) and why.
Written by each IMF refresh (services/reference/imf_fx.py).

Revision ID: fx_source_checks_20260926
Revises: fx_multisource_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "fx_source_checks_20260926"
down_revision: Union[str, None] = "fx_multisource_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS fx_source_checks (
            ccy          CHAR(3) NOT NULL,
            source       TEXT NOT NULL,
            reference    TEXT NOT NULL,
            n_compared   INTEGER NOT NULL,
            median_pct   NUMERIC(8, 3) NOT NULL,
            p95_pct      NUMERIC(8, 3) NOT NULL,
            max_pct      NUMERIC(8, 3) NOT NULL,
            verdict      TEXT NOT NULL,
            reason       TEXT,
            checked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (ccy, source, reference),
            CONSTRAINT ck_fx_check_verdict CHECK (verdict IN ('accepted', 'refused'))
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fx_source_checks")
