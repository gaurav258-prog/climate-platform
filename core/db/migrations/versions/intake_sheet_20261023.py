"""A batch says which sheet of its file it is (the product owner's decision of 2026-10-23: one standard workbook per
sector, every sheet received as its own batch through the same checks — services/intake/workbooks.py).

  ingest_batches  + sheet: the sheet of the stored workbook the batch was read from; NULL for a file read whole (a CSV,
                  a one-sheet Excel file, an API push) — so an approval or a held file's re-check reads the same rows

The downgrade drops the column.

Revision ID: intake_sheet_20261023
Revises: lookthrough_20261022
"""
from typing import Sequence, Union

from alembic import op

revision: str = "intake_sheet_20261023"
down_revision: Union[str, None] = "lookthrough_20261022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE ingest_batches ADD COLUMN sheet TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE ingest_batches DROP COLUMN sheet")
