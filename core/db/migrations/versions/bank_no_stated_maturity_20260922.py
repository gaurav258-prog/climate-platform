"""ext_banking gains no_stated_maturity -- the EBA Q&A 2022_6515 '>20yr bucket' signal

EBA Q&A 2022_6515 (Templates 1 & 5, maturity buckets): an exposure with no stated maturity for reasons
OTHER than the counterparty having the choice of the repayment date (equity holdings, perpetual instruments)
"shall be disclosed in the largest maturity bucket '>20 years'" -- never silently excluded from the maturity
columns. This is a genuinely different case from "we simply don't have residual_maturity_years for this loan
yet" (the existing, correctly-excluded-until-supplied gap) -- conflating the two would either wrongly count a
real data gap as if it were an intentional >20yr disclosure, or (the bug being fixed here) wrongly drop a
genuine no-stated-maturity exposure out of the maturity coverage stats entirely. Adding the real input (does
this exposure have no stated maturity by its own nature) lets services/governance/pillar3_templates.py route
it correctly, the same pattern used for counterparty_evic_eur / counterparty_govt_level.

Revision ID: bank_no_stated_maturity_20260922
Revises: a5083a25dd22
Create Date: 2026-09-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "bank_no_stated_maturity_20260922"
down_revision: Union[str, None] = "a5083a25dd22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = "ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS no_stated_maturity BOOLEAN;"
DOWNGRADE = "ALTER TABLE ext_banking DROP COLUMN IF EXISTS no_stated_maturity;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
