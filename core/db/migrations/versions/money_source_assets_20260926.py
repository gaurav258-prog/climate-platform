"""Where every stored amount on an asset came from (multi-currency phase 2).

  * portfolio_entities.money_source JSONB — {"fields": {field: {amount, currency, book_date, eur, policy, units_per_eur,
    source, basis, rate_date, stale, origin}}}: each money field of the asset (including its sector extension row) as
    the customer sent it, the rate that converted it, and the batch it came from. A later batch replaces only the
    fields it sent. (sc_sourcing_plots and the phase-1b tables already carry the same column and shape.)

Revision ID: money_source_assets_20260926
Revises: money_source_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "money_source_assets_20260926"
down_revision: Union[str, None] = "money_source_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE portfolio_entities ADD COLUMN IF NOT EXISTS money_source JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE portfolio_entities DROP COLUMN IF EXISTS money_source")
