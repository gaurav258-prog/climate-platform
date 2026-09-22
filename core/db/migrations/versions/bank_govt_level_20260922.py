"""ext_banking gains counterparty_govt_level — the EU Taxonomy Art. 7(1) GAR-exclusion scope signal

Del. Reg. (EU) 2021/2178 Art. 7(1) excludes ONLY exposures to central governments, central banks and
supranational issuers from the GAR numerator/denominator -- not local/regional government or compulsory
social security bodies. The GAR counterparty classifier (services/governance/pillar3_templates.py,
_gar_counterparty) previously swept the WHOLE of NACE section O ("Public administration and defence;
compulsory social security") into an excluded "General governments" bucket, wrongly excluding local/regional
government too. Fixed by adding the real input (which government level the counterparty is), the same pattern
used for counterparty_evic_eur (see bank_evic_20260922) -- not by softening the exclusion rule.

Revision ID: bank_govt_level_20260922
Revises: bank_evic_20260922
Create Date: 2026-09-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "bank_govt_level_20260922"
down_revision: Union[str, None] = "bank_evic_20260922"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = "ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS counterparty_govt_level TEXT;"
DOWNGRADE = "ALTER TABLE ext_banking DROP COLUMN IF EXISTS counterparty_govt_level;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
