"""Taxonomy DNSH / minimum-safeguards attestation flags

Revision ID: dnsh_flags_20260712
Revises: fx_rates_20260712
Create Date: 2026-07-12

EU Taxonomy ALIGNMENT requires, on top of eligibility: substantial contribution,
Do-No-Significant-Harm (DNSH) to the other five objectives, AND minimum
safeguards (OECD/UNGC). A large issuer's reported Article-8 aligned % already
embeds those by definition. But a manager may separately KNOW an issuer fails
DNSH or safeguards (an active controversy) and must then NOT count that issuer's
aligned figure.

So we store two nullable attestations per issuer disclosure:
  * dnsh_ok           — NULL = not separately assessed (take reported aligned as-is)
                        TRUE = confirmed / FALSE = known to fail → aligned excluded
  * min_safeguards_ok — same semantics for minimum safeguards
Only an explicit FALSE excludes; the default (NULL) preserves prior behaviour.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "dnsh_flags_20260712"
down_revision: Union[str, None] = "fx_rates_20260712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE issuer_esg_metrics
            ADD COLUMN dnsh_ok BOOLEAN,
            ADD COLUMN min_safeguards_ok BOOLEAN;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE issuer_esg_metrics
            DROP COLUMN IF EXISTS dnsh_ok,
            DROP COLUMN IF EXISTS min_safeguards_ok;
    """)
