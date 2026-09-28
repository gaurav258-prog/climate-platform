"""Intake phase 5: which data a filing is computed from, recorded on the filing.

regulatory_filing.view            joint (the book as resolved) | client (the client's own values) | tellumen (ours where
                                  we derive one) — the asset facts the engine read
regulatory_filing.figure_sources  per reported figure where both the client's attested number and ours exist:
                                  {datapoint: 'client' | 'tellumen'}. Refresh and restate keep both.

Revision ID: filing_views_20260928
Revises: engine_runs_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "filing_views_20260928"
down_revision: Union[str, None] = "engine_runs_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE regulatory_filing ADD COLUMN IF NOT EXISTS view TEXT NOT NULL DEFAULT 'joint'")
    op.execute("ALTER TABLE regulatory_filing ADD CONSTRAINT ck_filing_view CHECK (view IN ('joint', 'client', 'tellumen'))")
    op.execute("ALTER TABLE regulatory_filing ADD COLUMN IF NOT EXISTS figure_sources JSONB NOT NULL DEFAULT '{}'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE regulatory_filing DROP CONSTRAINT IF EXISTS ck_filing_view")
    op.execute("ALTER TABLE regulatory_filing DROP COLUMN IF EXISTS figure_sources")
    op.execute("ALTER TABLE regulatory_filing DROP COLUMN IF EXISTS view")
