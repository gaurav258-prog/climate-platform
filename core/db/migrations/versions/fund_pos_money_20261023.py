"""A fund position keeps where its amount came from (the product owner's decision of 2026-10-23: an asset manager's
holdings by ISIN are a book of its standard file, received through the governed intake — services/ingest/fund_books.py).

  fund_positions  + money_source: the amount as sent, its currency, the rate and date that converted it, and the batch —
                  as every other book's amounts keep it (services/intake/money.field_entry); NULL for positions
                  written before, or by the API, which keeps the native amount and currency in their own columns

The downgrade drops the column.

Revision ID: fund_pos_money_20261023
Revises: intake_sheet_20261023
"""
from typing import Sequence, Union

from alembic import op

revision: str = "fund_pos_money_20261023"
down_revision: Union[str, None] = "intake_sheet_20261023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE fund_positions ADD COLUMN money_source JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE fund_positions DROP COLUMN money_source")
