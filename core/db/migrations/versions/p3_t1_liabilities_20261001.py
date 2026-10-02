"""ext_banking.counterparty_total_liabilities_eur (+ its balance-sheet date) — the denominator of the proportion Annex XL
names for Pillar 3 Template 1 column i.

Annex XL, Template 1, column i (Implementing Regulation (EU) 2022/2453 and the EBA IT solutions under Implementing
Regulation (EU) 2024/3172, the same wording): 'Institutions shall estimate the scope 3 emissions per sector in a
proportionate manner, including by taking into account their exposures (loans and advances, debt securities and equity
holdings) towards the counterparty compared to the total liabilities (accounting liabilities and shareholders' equity)
of the counterparty.' The counterparty's total liabilities including shareholders' equity is a fact of its balance sheet
on a date; it is stated per exposure on the loan tape, as the counterparty's EVIC is (counterparty_evic_eur), with the
date of the balance sheet it is taken from (the date its currency is converted at). Positive, or not stated.

Revision ID: p3_t1_liabilities_20261001
Revises: eudr_label_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "p3_t1_liabilities_20261001"
down_revision: Union[str, None] = "eudr_label_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS counterparty_total_liabilities_eur NUMERIC(20,2)")
    op.execute("ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS counterparty_total_liabilities_date DATE")
    op.execute("ALTER TABLE ext_banking ADD CONSTRAINT ck_ext_banking_cp_total_liabilities CHECK ("
               "counterparty_total_liabilities_eur IS NULL OR (counterparty_total_liabilities_eur > 0 "
               "AND counterparty_total_liabilities_date IS NOT NULL))")


def downgrade() -> None:
    op.execute("ALTER TABLE ext_banking DROP CONSTRAINT IF EXISTS ck_ext_banking_cp_total_liabilities")
    op.execute("ALTER TABLE ext_banking DROP COLUMN IF EXISTS counterparty_total_liabilities_date")
    op.execute("ALTER TABLE ext_banking DROP COLUMN IF EXISTS counterparty_total_liabilities_eur")
