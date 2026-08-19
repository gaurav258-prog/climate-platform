"""taxonomy_evidence_fields

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-11

ml/regulatory/eu_taxonomy_classifier.py has always been honest that it can
only ever return "eligible", never "aligned" -- Article 3 also requires
substantial-contribution and minimum-safeguards evidence the platform never
collected. This adds somewhere to put that evidence when a tenant provides
it, rather than changing the classifier's honesty stance by fiat:

- portfolio_entities.borrower_entity_id / minimum_safeguards_status: the
  counterparty-level OECD/UN/ILO compliance flag (Article 18) a bank's own
  KYC/ESG vendor already produces -- applies to every vertical alike, since
  it's a property of the borrower/counterparty, not the physical asset, so
  it lives on the shared table rather than one ext_* table.
- ext_realestate.epc_rating: the building's Energy Performance Certificate
  grade, the technical-screening-criteria evidence Annex I §7.7 requires for
  substantial contribution (real-estate-specific -- other verticals' Annex I
  activities use different criteria, e.g. generation-source mix for energy,
  not modeled here since no demo vertical currently needs it).

Both are optional (nullable): most uploads still won't carry this data, and
the classifier keeps returning "eligible" with an honest unverified note
until they do -- see the classifier's own verified/note fields.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
ALTER TABLE portfolio_entities ADD COLUMN borrower_entity_id VARCHAR(20);
ALTER TABLE portfolio_entities ADD COLUMN minimum_safeguards_status VARCHAR(20)
    CHECK (minimum_safeguards_status IN ('compliant', 'non_compliant') OR minimum_safeguards_status IS NULL);
ALTER TABLE ext_realestate ADD COLUMN epc_rating VARCHAR(2)
    CHECK (epc_rating IN ('A', 'B', 'C', 'D', 'E', 'F', 'G') OR epc_rating IS NULL);
"""

DOWNGRADE = """
ALTER TABLE ext_realestate DROP COLUMN IF EXISTS epc_rating;
ALTER TABLE portfolio_entities DROP COLUMN IF EXISTS minimum_safeguards_status;
ALTER TABLE portfolio_entities DROP COLUMN IF EXISTS borrower_entity_id;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
