"""Customer data intake — currency and book date on every batch (multi-currency review, phase 1).

  * ingest_batches.currency — the currency the sender declared for the file's amounts (a row's `currency` column or
    a mapping's per-field currency overrides it); never assumed.
  * ingest_batches.book_date — the date the figures describe; rates are taken for it (balances: closing rate;
    annual flows: average of the 12 months to it). An approval replays the batch at the same date.
  * ingest_batches.money_report — every rate used (currency, closing/average, source, kind, date, age, stale).
  * intake_channels.currency — a drop folder's declared currency (its files carry their own book_date column).

Revision ID: intake_currency_20260926
Revises: fx_peg_stn_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "intake_currency_20260926"
down_revision: Union[str, None] = "fx_peg_stn_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""ALTER TABLE ingest_batches ADD COLUMN IF NOT EXISTS currency CHAR(3),
                                             ADD COLUMN IF NOT EXISTS book_date DATE,
                                             ADD COLUMN IF NOT EXISTS money_report JSONB""")
    op.execute("ALTER TABLE intake_channels ADD COLUMN IF NOT EXISTS currency CHAR(3)")


def downgrade() -> None:
    op.execute("ALTER TABLE intake_channels DROP COLUMN IF EXISTS currency")
    op.execute("ALTER TABLE ingest_batches DROP COLUMN IF EXISTS money_report, DROP COLUMN IF EXISTS book_date, DROP COLUMN IF EXISTS currency")
