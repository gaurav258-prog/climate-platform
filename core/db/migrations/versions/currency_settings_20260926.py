"""Currency settings (multi-currency phase 2): the organisation's presentation currency and each legal entity's
functional currency.

  * org_reporting_settings.presentation_currency — the currency the organisation presents in (group / consolidated
    filings, the screens). Governed like the rest of the reporting basis (audited; 4-eyes when the matrix says so).
  * reporting_entities.functional_currency — the currency an entity keeps its books and files SOLO in; blank =
    inherited from its parent, and at the top from the organisation's presentation currency.

Revision ID: currency_settings_20260926
Revises: fx_rate_history_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "currency_settings_20260926"
down_revision: Union[str, None] = "fx_rate_history_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE org_reporting_settings ADD COLUMN IF NOT EXISTS presentation_currency CHAR(3)")
    op.execute("ALTER TABLE reporting_entities ADD COLUMN IF NOT EXISTS functional_currency CHAR(3)")


def downgrade() -> None:
    op.execute("ALTER TABLE reporting_entities DROP COLUMN IF EXISTS functional_currency")
    op.execute("ALTER TABLE org_reporting_settings DROP COLUMN IF EXISTS presentation_currency")
