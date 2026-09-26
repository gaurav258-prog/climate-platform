"""Where each converted amount came from — on every table fed by an input outside the intake pipeline.

  * <table>.money_source JSONB — {currency, book_date, native: {field: amount}, rates: [{currency, policy, units_per_eur,
    source, basis, rate_date, stale}]}: the amounts as the customer sent them and the exact rates used to convert them
    (multi-currency review, phase 1b). Tables: gl_balance, loan_arrears, sc_company_sites, sc_sourcing_plots,
    insurer_incurred_losses, issuer_emissions, ext_banking.

Revision ID: money_source_20260926
Revises: intake_currency_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "money_source_20260926"
down_revision: Union[str, None] = "intake_currency_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("gl_balance", "loan_arrears", "sc_company_sites", "sc_sourcing_plots", "insurer_incurred_losses",
          "issuer_emissions", "ext_banking")


def upgrade() -> None:
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS money_source JSONB")


def downgrade() -> None:
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS money_source")
