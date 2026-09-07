"""portfolio_entities.external_ref — the source system's own identifier for a row (loan / instrument / policy id).

Lets every derived figure be traced back to the record it came from: a supervisor opening a rebuilt template cell
sees the instrument ids behind it; a bank sees its own loan ids. Nullable; free text.

Revision ID: pe_external_ref_20260907
Revises: sup_shadow_20260907
"""
from typing import Sequence, Union

from alembic import op

revision: str = "pe_external_ref_20260907"
down_revision: Union[str, None] = "sup_shadow_20260907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE portfolio_entities ADD COLUMN IF NOT EXISTS external_ref TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE portfolio_entities DROP COLUMN IF EXISTS external_ref")
