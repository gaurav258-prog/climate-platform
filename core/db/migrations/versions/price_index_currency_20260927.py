"""Multi-currency phase 4: every commodity price series states its currency.

The World Bank Pink Sheet and USDA quote in US dollars; the EU agri-food portal in euro. Input-cost pressure applied the
dollar price move straight to euro spend — for a euro buyer the cost move is the price move AND the dollar's move.
Backfilled from the unit and source; a series whose currency can't be told stays NULL and is reported, never guessed.

Revision ID: price_index_currency_20260927
Revises: consolidation_fx_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "price_index_currency_20260927"
down_revision: Union[str, None] = "consolidation_fx_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE commodity_price_index ADD COLUMN IF NOT EXISTS currency CHAR(3)")
    op.execute("""
        UPDATE commodity_price_index SET currency = CASE
            WHEN unit ILIKE '$%' OR unit ILIKE 'USD%' OR unit ILIKE 'US$%' THEN 'USD'
            WHEN unit ILIKE '€%' OR unit ILIKE 'EUR%' OR unit ILIKE 'Euro%' THEN 'EUR'
            WHEN source ILIKE 'EU Commission%' THEN 'EUR'
            WHEN source ILIKE 'World Bank%' OR source ILIKE 'USDA%' THEN 'USD'
        END WHERE currency IS NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE commodity_price_index DROP COLUMN IF EXISTS currency")
