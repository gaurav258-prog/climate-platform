"""ext_realestate gains annual_gross_rental_revenue_eur — the real Taxonomy turnover denominator

Del. Reg. (EU) 2021/2178 Annex I §1.1.1: the turnover KPI denominator is net turnover as defined in
Article 2, point (5) of Directive 2013/34/EU -- revenue recognised under IAS 1 para 82(a), i.e. GROSS
revenue before operating expenses. reit_taxonomy.py was using annual_noi_eur (revenue MINUS opex) as
the turnover base, a systematic understatement. This adds the real gross-revenue field so it can be
supplied per property; annual_noi_eur remains for the NOI-impact calc it was always meant for.

Revision ID: reit_gross_revenue_20260922
Revises: bank_evic_20260922
Create Date: 2026-09-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "reit_gross_revenue_20260922"
down_revision: Union[str, None] = "bank_evic_20260922"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = "ALTER TABLE ext_realestate ADD COLUMN IF NOT EXISTS annual_gross_rental_revenue_eur NUMERIC;"
DOWNGRADE = "ALTER TABLE ext_realestate DROP COLUMN IF EXISTS annual_gross_rental_revenue_eur;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
