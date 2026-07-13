"""FX normalization — fx_rates table + position native currency/value

Revision ID: fx_rates_20260712
Revises: taxonomy_align_20260712
Create Date: 2026-07-12

A fund can hold non-EUR lines (USD, GBP, JPY …). SFDR figures roll up in EUR, so
each position must be converted at its as-of date. We store:
  * fx_rates: EUR-per-one-unit-of-currency, dated (ECB reference rates).
  * fund_positions.currency + market_value_base: the ORIGINAL currency and value,
    so the EUR figure is auditable back to its source and rate.

Seeded with the ECB 2023-12-29 reference set so tests/offline runs are
deterministic; scripts/load_fx_rates.py pulls live history over the top.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "fx_rates_20260712"
down_revision: Union[str, None] = "taxonomy_align_20260712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# EUR per 1 unit of currency — ECB reference rates 2023-12-29 (kept in sync with
# services/reference/fx.py FALLBACK_EUR_PER_UNIT).
_SEED = {
    "USD": 0.90580, "GBP": 1.15130, "CHF": 1.08000, "JPY": 0.0063967,
    "SEK": 0.090123, "NOK": 0.088964, "DKK": 0.134176, "CAD": 0.683000,
    "AUD": 0.614900, "CNY": 0.127374, "HKD": 0.115856, "SGD": 0.685350,
    "PLN": 0.230442, "CZK": 0.040477, "HUF": 0.0026080, "NZD": 0.573100,
}


def upgrade() -> None:
    op.execute("""
        CREATE TABLE fx_rates (
            ccy          VARCHAR(3) NOT NULL,
            rate_date    DATE NOT NULL,
            eur_per_unit NUMERIC(18,8) NOT NULL,   -- EUR value of one unit of ccy
            source       VARCHAR(20) NOT NULL DEFAULT 'ecb',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (ccy, rate_date)
        );
        CREATE INDEX ix_fx_rates_ccy_date ON fx_rates(ccy, rate_date DESC);

        ALTER TABLE fund_positions
            ADD COLUMN currency VARCHAR(3) NOT NULL DEFAULT 'EUR';
    """)
    values = ", ".join(
        f"('{c}', DATE '2023-12-29', {r}, 'seed')" for c, r in _SEED.items()
    )
    op.execute(f"INSERT INTO fx_rates (ccy, rate_date, eur_per_unit, source) VALUES {values};")


def downgrade() -> None:
    op.execute("""
        ALTER TABLE fund_positions DROP COLUMN IF EXISTS currency;
        DROP TABLE IF EXISTS fx_rates;
    """)
