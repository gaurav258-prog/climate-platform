"""Multi-currency phase 4: fund_positions.market_value_base → market_value_native.

The column holds each position's value in the currency it was SENT in (fund_positions.currency) — not the fund's base
currency (funds.base_currency) — and the name said the opposite. Renamed so nobody sums it as a fund-currency figure.

Revision ID: fund_native_value_20260927
Revises: prior_units_20260927
"""
from typing import Sequence, Union

from alembic import op

revision: str = "fund_native_value_20260927"
down_revision: Union[str, None] = "prior_units_20260927"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE fund_positions RENAME COLUMN market_value_base TO market_value_native")
    op.execute("COMMENT ON COLUMN fund_positions.market_value_native IS "
               "'value in fund_positions.currency, as sent (NULL when a position was aggregated from lots in several currencies)'")


def downgrade() -> None:
    op.execute("ALTER TABLE fund_positions RENAME COLUMN market_value_native TO market_value_base")
