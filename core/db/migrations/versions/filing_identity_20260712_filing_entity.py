"""filing_identity — the reporting-entity fields SFDR needs to actually submit

Revision ID: filing_identity_20260712
Revises: esg_metrics_20260712
Create Date: 2026-07-12

A structurally-complete PAI statement still can't be FILED without the reporting
entity's identity. SFDR's Annex I template header requires the financial market
participant's name and LEI and the reference period. So:

  * organizations (the manager / FMP): lei, legal_name, filing_contact_email.
    Domicile is the existing `country` column.
  * funds: lei (a fund may carry its own LEI; used by the Art 8/9 periodic report).

Nothing is inferred — a filing is only marked "ready to file" once the manager
supplies these, and the manager LEI is validated against GLEIF (real, active).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "filing_identity_20260712"
down_revision: Union[str, None] = "esg_metrics_20260712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE organizations
            ADD COLUMN lei VARCHAR(20),
            ADD COLUMN legal_name VARCHAR(300),
            ADD COLUMN filing_contact_email VARCHAR(200);
        ALTER TABLE funds ADD COLUMN lei VARCHAR(20);
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE funds DROP COLUMN IF EXISTS lei;
        ALTER TABLE organizations
            DROP COLUMN IF EXISTS lei,
            DROP COLUMN IF EXISTS legal_name,
            DROP COLUMN IF EXISTS filing_contact_email;
    """)
