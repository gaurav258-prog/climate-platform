"""ext_banking gains counterparty EVIC — the PCAF attribution denominator

Real PCAF-attributed financed emissions needs each counterparty's EVIC (Enterprise Value Including Cash):
attribution factor = min(outstanding loan balance / EVIC, 1.0), the same formula already used for asset
managers (services/fund_disclosure.py). Without it the bank KRI could only show an unweighted Scope 1-3 sum
mislabelled as PCAF -- fixed by adding the real input, not by watering down the label.

Revision ID: bank_evic_20260922
Revises: loan_arrears_country_20260922
Create Date: 2026-09-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "bank_evic_20260922"
down_revision: Union[str, None] = "loan_arrears_country_20260922"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = "ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS counterparty_evic_eur NUMERIC;"
DOWNGRADE = "ALTER TABLE ext_banking DROP COLUMN IF EXISTS counterparty_evic_eur;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
