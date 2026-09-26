"""Add the São Tomé and Príncipe dobra's euro peg: 24.5 STN per EUR since the 2018 redenomination (1 STN = 1,000 STD;
the dobra has been pegged to the euro at 24,500 STD under the 2009 economic cooperation agreement with Portugal).

Revision ID: fx_peg_stn_20260926
Revises: fx_source_checks_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "fx_peg_stn_20260926"
down_revision: Union[str, None] = "fx_source_checks_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""INSERT INTO fx_pegs (ccy, units_per_eur, valid_from, valid_to, legal_basis)
                  VALUES ('STN', 24.5, '2018-01-01', NULL,
                          'Peg of the dobra to the euro — 2009 economic cooperation agreement between Portugal and São Tomé and '
                          'Príncipe (Banco Central de São Tomé e Príncipe); 24.5 STN = 1 EUR since the 2018 redenomination')
                  ON CONFLICT (ccy, valid_from) DO NOTHING""")


def downgrade() -> None:
    op.execute("DELETE FROM fx_pegs WHERE ccy = 'STN' AND valid_from = '2018-01-01'")
