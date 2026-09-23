"""Consolidation-method guardrail — C2 in the 2026-09-23 independent consolidation-scope review.

`consolidation_method` was unconstrained beyond the METHODS set check: an admin could tag a 30%-owned stake
'full' and the whole book (VaR, financed emissions, Taxonomy) silently consolidates at 100%, no guardrail, no
audit trail for the choice. IFRS 10 control is genuinely principles-based, not a raw ownership% cutoff, so
this doesn't hard-block any (method, ownership_pct) combination — it requires an explicit, disclosed reason
only when the choice runs counter to the ownership%-implied presumption (full consolidation below majority
ownership, or proportional/equity consolidation of a majority-owned stake), mirroring the solo_waiver_reason
pattern from the C1 fix.

Revision ID: consolidation_basis_20260923
Revises: solo_consolidated_20260923
"""
import sqlalchemy as sa
from alembic import op

revision = "consolidation_basis_20260923"
down_revision = "solo_consolidated_20260923"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reporting_entities", sa.Column("consolidation_basis", sa.Text, nullable=True))


def downgrade():
    op.drop_column("reporting_entities", "consolidation_basis")
