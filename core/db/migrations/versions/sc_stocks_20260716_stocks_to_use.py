"""Per-YEAR world stocks-to-use (USDA PSD), replacing a single static number per commodity

Revision ID: sc_stocks_20260716
Revises: coffee_demote_20260716
Create Date: 2026-07-16

WHY. Price amplification A(s) = (34.7/s)^3.62 is the most leveraged term in the whole chain —
it is what turns a few-percent supply shock into a doubled price when the market is tight. We
fed it ONE STATIC NUMBER per commodity, hand-entered. Two things are wrong with that:

  1. THE NUMBERS WERE WRONG. Coffee's world stocks-to-use in 2021 was 14.2% (USDA PSD). We
     used 40.0%. A(40) = 0.60 (dampening); A(14.2) hits the 6.0 cap. A ~10x error on the most
     leveraged term in the model.
  2. STOCKS ARE NOT A CONSTANT. They move violently year to year — coffee 18.3 -> 17.0 ->
     19.6 -> 14.2 -> 14.2 -> 11.7 -> 10.1 across 2018-24; almonds 19.2 -> 41.9 -> 22.4. The
     amplification must use the stocks AT THE EVENT, not a decade-average guess.

AND IT EXPLAINS THE COFFEE PUZZLE. We could not see how a -5.94% world shock produced 2021's
+44-60% price move. It did — because stocks were at 14.2%, not 40%. Our chain instead used a
38.5% yield shock (13x the real -2.9% climate share) multiplied by a 10x-too-small
amplification. TWO COMPENSATING ERRORS that cancelled into a plausible price. The model got
roughly the right answer for entirely the wrong reasons, which is exactly the failure mode a
backtest is supposed to catch and did not — because the backtest only checked the final price.

sc_commodity_stocks holds the real series; sc_commodities.stock_to_use stays as the fallback
for commodities PSD does not cover. NOTE PSD DOES NOT TRACK COCOA (that is ICCO's domain), so
cocoa — our one published crop — keeps its hand-entered 26.4% and that remains a known gap.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sc_stocks_20260716"
down_revision: Union[str, None] = "coffee_demote_20260716"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sc_commodity_stocks (
            commodity          VARCHAR(80) NOT NULL,
            market_year        INT NOT NULL,
            ending_stocks      NUMERIC(18,3),
            domestic_use       NUMERIC(18,3),
            stocks_to_use_pct  NUMERIC(8,3) NOT NULL,
            unit               VARCHAR(40),
            source             VARCHAR(60) NOT NULL,
            note               TEXT,
            ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (commodity, market_year, source)
        );
        CREATE INDEX ix_sc_commodity_stocks_lookup ON sc_commodity_stocks(commodity, market_year);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sc_commodity_stocks;")
