"""Partial index for the data version behind the asset-points memo: max(scored_at) over the CURRENT scores must be
an index probe, not a scan of every score ever written.

Revision ID: scores_current_index_20260909
Revises: hazard_relevance_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "scores_current_index_20260909"
down_revision: Union[str, None] = "hazard_relevance_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_canonical_scores_current_scored_at ON canonical_scores (scored_at DESC) WHERE valid_to IS NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_canonical_scores_current_scored_at")
