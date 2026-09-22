"""loan_arrears gains an optional ISO-2 country

The seasonal-arrears overlay only had a calendar check (crop -> harvest months). To add a climate-attributed
tier (was this crop's arrears explained by an OBSERVED national yield shock, from crop_yield_observations,
FAOSTAT-grade), the loan needs a country to join on. `region` stays free text (a bank's own sub-national label,
e.g. 'Castilla') and is never guessed into a country - country is a new, optional, explicit field.

Revision ID: loan_arrears_country_20260922
Revises: agrifood_shadow_book_20260912
Create Date: 2026-09-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "loan_arrears_country_20260922"
down_revision: Union[str, None] = "agrifood_shadow_book_20260912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = "ALTER TABLE public.loan_arrears ADD COLUMN IF NOT EXISTS country VARCHAR(3);"
DOWNGRADE = "ALTER TABLE public.loan_arrears DROP COLUMN IF EXISTS country;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
