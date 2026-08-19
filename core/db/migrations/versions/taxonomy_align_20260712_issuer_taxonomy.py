"""issuer taxonomy alignment — per-issuer reported eligible/aligned %

Revision ID: taxonomy_align_20260712
Revises: narratives_20260712
Create Date: 2026-07-12

EU Taxonomy ALIGNMENT (not just eligibility) requires: substantial contribution
to ≥1 of the six environmental objectives, Do-No-Significant-Harm to the other
five, and minimum safeguards. We do NOT assess those ourselves — instead large
EU companies report their own Taxonomy-eligible and Taxonomy-aligned % of revenue
under Article 8 of the Taxonomy Regulation, and a manager collects those figures.

So alignment is stored as a per-issuer, org-scoped DISCLOSURE (like emissions):
the issuer's reported eligible/aligned %. The fund figure is the value-weighted
roll-up over holdings that supplied it, with coverage disclosed. Where no issuer
figure is supplied, we still never assert 'aligned' — it stays eligible-at-most.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "taxonomy_align_20260712"
down_revision: Union[str, None] = "narratives_20260712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE issuer_esg_metrics
            ADD COLUMN taxonomy_eligible_pct NUMERIC(6,3),
            ADD COLUMN taxonomy_aligned_pct  NUMERIC(6,3);
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE issuer_esg_metrics
            DROP COLUMN IF EXISTS taxonomy_eligible_pct,
            DROP COLUMN IF EXISTS taxonomy_aligned_pct;
    """)
