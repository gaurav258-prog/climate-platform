"""Agri-food supervisor shadow book: sc_sourcing_plots gains the same own/shadow split portfolio_entities has.

The independent lens for the agri-food authority rebuilds the sourcing_by_origin template from the authority's
own granular data (the EUDR sourcing-plot extract) — the same shape as a bank's AnaCredit extract, but
agriculture deliberately keeps its own book (sc_sourcing_plots), not the shared financial portfolio engine
(see services/portfolio_engine.py's docstring on why a bill-of-materials graph does not belong in that engine).
So the shadow copy of a supervised operator's plots lives here too: `source` ('own' | 'supervisor_shadow') and
`subject_org_id` (which operator this regulator's shadow rows describe), mirroring portfolio_entities exactly —
existing rows default to source='own', subject_org_id NULL, so no operator's own book is affected.

Revision ID: agrifood_shadow_book_20260912
Revises: approvals_policy_off_20260912
"""
from typing import Sequence, Union

from alembic import op

revision: str = "agrifood_shadow_book_20260912"
down_revision: Union[str, Sequence[str], None] = "approvals_policy_off_20260912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE sc_sourcing_plots ADD COLUMN IF NOT EXISTS source VARCHAR(30) NOT NULL DEFAULT 'own'")
    op.execute("ALTER TABLE sc_sourcing_plots ADD COLUMN IF NOT EXISTS subject_org_id UUID NULL "
               "REFERENCES organizations(org_id) ON DELETE CASCADE")
    op.execute("ALTER TABLE sc_sourcing_plots DROP CONSTRAINT IF EXISTS ck_sc_plots_source")
    op.execute("ALTER TABLE sc_sourcing_plots ADD CONSTRAINT ck_sc_plots_source "
               "CHECK (source IN ('own', 'supervisor_shadow'))")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sc_plots_shadow ON sc_sourcing_plots (org_id, source, subject_org_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sc_plots_shadow")
    op.execute("ALTER TABLE sc_sourcing_plots DROP CONSTRAINT IF EXISTS ck_sc_plots_source")
    op.execute("ALTER TABLE sc_sourcing_plots DROP COLUMN IF EXISTS subject_org_id")
    op.execute("ALTER TABLE sc_sourcing_plots DROP COLUMN IF EXISTS source")
