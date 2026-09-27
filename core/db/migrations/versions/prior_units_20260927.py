"""Multi-currency phase 4: prior-filing figures carry a normalised unit.

The XBRL reader stored the raw unitRef id ('uEUR', 'u-EUR', 'tco2e', 'upure'); the readers now resolve units to one
vocabulary (ISO code for money, '%', 'pure', 'tCO2e', 'MWh'…). This brings figures already read onto it, so a series
never splits (or merges) on a spelling.

Revision ID: prior_units_20260927
Revises: price_index_currency_20260927
"""
from typing import Sequence, Union

from alembic import op

revision: str = "prior_units_20260927"
down_revision: Union[str, None] = "price_index_currency_20260927"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE reported_figure SET unit = CASE
            WHEN upper(regexp_replace(unit, '^(u-?|iso4217:)', '', 'i')) IN (
                     'EUR','USD','GBP','CHF','JPY','SEK','NOK','DKK','PLN','CZK','HUF','RON','BGN','ISK','CAD','AUD',
                     'NZD','CNY','HKD','SGD','INR','BRL','ZAR','MXN','KRW','TRY','ILS','AED','SAR')
                THEN upper(regexp_replace(unit, '^(u-?|iso4217:)', '', 'i'))
            WHEN lower(unit) IN ('pure', 'upure', 'u-pure', 'xbrli:pure') THEN 'pure'
            WHEN lower(unit) ~ '^u?-?tco2e?q?$' THEN 'tCO2e'
            WHEN lower(unit) ~ '^u?-?mwh$' THEN 'MWh'
            ELSE unit END
        WHERE unit IS NOT NULL
    """)


def downgrade() -> None:
    pass    # the raw ids are not recoverable and not needed
