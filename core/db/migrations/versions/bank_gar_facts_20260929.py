"""ext_banking gains the per-exposure facts Pillar 3 Templates 2, 7, 8 and 9 are built from (spec its_2024_3172).

instrument_type             FINREP instrument: loans_and_advances / debt_securities / equity_instruments / derivatives /
                            on_demand_interbank / cash / other_assets (Template 7 rows by instrument; excluded asset rows)
counterparty_subsector      of an other financial corporation: investment_firm / management_company / insurance_undertaking
nfrd_subject                the counterparty is subject to the non-financial reporting (NFRD / CSRD) disclosure obligations
loan_purpose                building_renovation / motor_vehicle / housing / other (household and local-government rows)
trading_book                held for trading (excluded from both GAR numerator and denominator)
taxonomy_objective          ccm / cca — the environmental objective an eligible / aligned exposure contributes to
taxonomy_contribution       transitional / enabling / adaptation / none (Template 7 'of which' columns)
specialised_lending         the exposure is specialised lending (Template 7 'of which specialised lending')
ep_score_kwh_m2             the collateral's energy performance, kWh/m² (Template 2 columns b-g)
ep_score_estimated          that EP score is the institution's estimate, not from an EPC (Template 2 column p, rows 5 and 10)

Revision ID: bank_gar_facts_20260929
Revises: regspec_sole_reviewer_20260929
"""
from typing import Sequence, Union

from alembic import op

revision: str = "bank_gar_facts_20260929"
down_revision: Union[str, None] = "regspec_sole_reviewer_20260929"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _in(col: str, values: tuple) -> str:
    return f"TEXT CONSTRAINT ck_ext_banking_{col} CHECK ({col} IN ({', '.join(repr(v) for v in values)}))"


_COLS = (
    ("instrument_type", _in("instrument_type", ("loans_and_advances", "debt_securities", "equity_instruments", "derivatives",
                                                "on_demand_interbank", "cash", "other_assets"))),
    ("counterparty_subsector", _in("counterparty_subsector", ("investment_firm", "management_company", "insurance_undertaking"))),
    ("nfrd_subject", "BOOLEAN"),
    ("loan_purpose", _in("loan_purpose", ("building_renovation", "motor_vehicle", "housing", "other"))),
    ("trading_book", "BOOLEAN"),
    ("taxonomy_objective", _in("taxonomy_objective", ("ccm", "cca"))),
    ("taxonomy_contribution", _in("taxonomy_contribution", ("transitional", "enabling", "adaptation", "none"))),
    ("specialised_lending", "BOOLEAN"),
    ("ep_score_kwh_m2", "NUMERIC(10,2) CONSTRAINT ck_ext_banking_ep_score CHECK (ep_score_kwh_m2 >= 0)"),
    ("ep_score_estimated", "BOOLEAN"),
)


def upgrade() -> None:
    for name, kind in _COLS:
        op.execute(f"ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS {name} {kind}")


def downgrade() -> None:
    for name, _ in _COLS:
        op.execute(f"ALTER TABLE ext_banking DROP COLUMN IF EXISTS {name}")
