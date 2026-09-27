"""Multi-currency phase 3: filings in their own currency, and group-internal exposures.

  * portfolio_entities.intragroup_entity_id — the asset / exposure is with ANOTHER company of the same group (an
    intragroup loan, a property let to a sister company, a policy covering a group site). A solo filing keeps it; a
    consolidated filing that contains both sides eliminates it. Removing the entity clears the mark.
  * regulatory_filing.presentation_currency — the currency the filing presents its money in: a solo filing in the
    entity's functional currency, a consolidated filing in the group's presentation currency. NULL on filings frozen
    before this existed (they were all in EUR).

Revision ID: consolidation_fx_20260926
Revises: fx_client_rates_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "consolidation_fx_20260926"
down_revision: Union[str, None] = "fx_client_rates_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE portfolio_entities ADD COLUMN IF NOT EXISTS intragroup_entity_id UUID
            REFERENCES reporting_entities(entity_id) ON DELETE SET NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolio_entities_intragroup ON portfolio_entities (intragroup_entity_id) "
               "WHERE intragroup_entity_id IS NOT NULL")
    op.execute("ALTER TABLE regulatory_filing ADD COLUMN IF NOT EXISTS presentation_currency CHAR(3)")


def downgrade() -> None:
    op.execute("ALTER TABLE regulatory_filing DROP COLUMN IF EXISTS presentation_currency")
    op.execute("DROP INDEX IF EXISTS ix_portfolio_entities_intragroup")
    op.execute("ALTER TABLE portfolio_entities DROP COLUMN IF EXISTS intragroup_entity_id")
