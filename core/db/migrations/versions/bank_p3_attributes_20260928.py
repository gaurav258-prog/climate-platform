"""ext_banking gains the per-loan facts Pillar 3 Templates 1 and 5 are built from (spec its_2024_3172).

counterparty_sector          FINREP counterparty sector (Annex V, Part 1): the sector rows of Templates 1 and 5 cover
                             exposures towards non-financial corporations only
immovable_collateral         residential / commercial immovable property, or repossessed: Template 5 rows 10-12
accumulated_impairment_eur   accumulated impairment, negative fair-value changes due to credit risk and provisions
                             (Template 1 f-h, Template 5 m-o)
pab_excluded                 counterparty excluded from EU Paris-aligned Benchmarks, Reg. (EU) 2020/1818 Art 12(1)(d)-(g)
                             and 12(2) (Template 1 b)
ccm_sustainable              exposure environmentally sustainable for climate change mitigation (Template 1 c)
emissions_company_reported   the counterparty's emissions come from its own reporting (Template 1 k)

Revision ID: bank_p3_attributes_20260928
Revises: regspec_signoff_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "bank_p3_attributes_20260928"
down_revision: Union[str, None] = "regspec_signoff_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = (
    ("counterparty_sector", "TEXT CONSTRAINT ck_ext_banking_cp_sector CHECK (counterparty_sector IN ('central_bank', "
     "'general_government', 'credit_institution', 'other_financial_corporation', 'non_financial_corporation', 'household'))"),
    ("immovable_collateral", "TEXT CONSTRAINT ck_ext_banking_immovable CHECK (immovable_collateral IN ('residential', "
     "'commercial', 'repossessed', 'none'))"),
    ("accumulated_impairment_eur", "NUMERIC(18,2)"),
    ("pab_excluded", "BOOLEAN"),
    ("ccm_sustainable", "BOOLEAN"),
    ("emissions_company_reported", "BOOLEAN"),
)


def upgrade() -> None:
    for name, kind in _COLS:
        op.execute(f"ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS {name} {kind}")


def downgrade() -> None:
    for name, _ in _COLS:
        op.execute(f"ALTER TABLE ext_banking DROP COLUMN IF EXISTS {name}")
