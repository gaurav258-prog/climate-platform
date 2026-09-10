"""Partial index (h3_cell, scored_at) on current scores — the per-organisation data version behind the asset-points
memo becomes an index probe per cell instead of a scan.

Revision ID: scores_cell_scored_at_20260910
Revises: cold_wave_20260910
"""
from typing import Sequence, Union

from alembic import op

revision: str = "scores_cell_scored_at_20260910"
down_revision: Union[str, None] = "cold_wave_20260910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_canonical_scores_cell_scored_at ON canonical_scores (h3_cell, scored_at DESC) WHERE valid_to IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolio_entities_org_vertical_source ON portfolio_entities (org_id, vertical, source)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_canonical_scores_cell_scored_at; DROP INDEX IF EXISTS ix_portfolio_entities_org_vertical_source")
