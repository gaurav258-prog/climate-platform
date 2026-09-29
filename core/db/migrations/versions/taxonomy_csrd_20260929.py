"""ext_banking.csrd_subject — whether an exposure's counterparty is subject to the CSRD disclosure obligations.

Annex VI to Delegated Regulation (EU) 2021/2178 as replaced by Delegated Regulation (EU) 2026/73 splits undertakings by
the Corporate Sustainability Reporting Directive (Directive (EU) 2022/2464) where the earlier versions split them by the
Non-Financial Reporting Directive (nfrd_subject). They are different legal facts, so each is stated on its own.

Revision ID: taxonomy_csrd_20260929
Revises: taxonomy_cp_kpi_20260929
"""
from typing import Sequence, Union

from alembic import op

revision: str = "taxonomy_csrd_20260929"
down_revision: Union[str, None] = "taxonomy_cp_kpi_20260929"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS csrd_subject BOOLEAN")


def downgrade() -> None:
    op.execute("ALTER TABLE ext_banking DROP COLUMN IF EXISTS csrd_subject")
