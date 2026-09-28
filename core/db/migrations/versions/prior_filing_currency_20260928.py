"""A prior filing states the currency its money is reported in (resolves shared symbols such as '$') and its period
end (the date its money converts at in trends — until now guessed as 31 December of the label's year).

Revision ID: prior_filing_currency_20260928
Revises: entity_lei_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "prior_filing_currency_20260928"
down_revision: Union[str, None] = "entity_lei_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE reported_filing ADD COLUMN IF NOT EXISTS currency CHAR(3)")


def downgrade() -> None:
    op.execute("ALTER TABLE reported_filing DROP COLUMN IF EXISTS currency")
