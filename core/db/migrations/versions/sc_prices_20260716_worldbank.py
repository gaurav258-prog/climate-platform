"""Monthly commodity prices (World Bank Pink Sheet) — the chain's output, finally measured

Revision ID: sc_prices_20260716
Revises: sc_stocks_20260716
Create Date: 2026-07-16

The price move is what every calibration is SCORED against, and we had no price series at all
— every "observed" move in sc_model_validation was hand-typed from a press article. That is
how cocoa came to be validated against an observed "+177%" that no reference series
reproduces (World Bank/ICCO crop-year 2023/24 = +115.8%; calendar-2024 = +123.4%).

MONTHLY, deliberately: crop-year vs calendar-year vs peak give three defensible numbers for
one event, and quoting the wrong one fits a calibration to a fiction. Aggregate at the call
site, on a stated convention.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sc_prices_20260716"
down_revision: Union[str, None] = "sc_stocks_20260716"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sc_commodity_prices (
            commodity   VARCHAR(80) NOT NULL,
            year        INT NOT NULL,
            month       INT NOT NULL CHECK (month BETWEEN 1 AND 12),
            price       NUMERIC(18,6) NOT NULL,
            unit        VARCHAR(40),
            source      VARCHAR(60) NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (commodity, year, month, source)
        );
        CREATE INDEX ix_sc_commodity_prices_lookup ON sc_commodity_prices(commodity, year, month);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sc_commodity_prices;")
