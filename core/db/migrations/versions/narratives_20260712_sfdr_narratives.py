"""sfdr_narratives — the qualitative filing sections SFDR requires

Revision ID: narratives_20260712
Revises: sfdr_filings_20260712
Create Date: 2026-07-12

The SFDR PAI statement is not only a numbers table — Annex I also mandates
NARRATIVE sections: the policies to identify and prioritise principal adverse
impacts, the actions taken and planned, engagement policies, and references to
international standards. These are text the manager authors; we store them on the
organization (the financial market participant) so every fund's statement carries
them, and flag any that are missing rather than leaving the filing silently
incomplete.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "narratives_20260712"
down_revision: Union[str, None] = "sfdr_filings_20260712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE organizations ADD COLUMN sfdr_narratives JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS sfdr_narratives")
