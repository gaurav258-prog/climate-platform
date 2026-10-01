"""issuer_transition_scores is retired: it held one transition score per issuer for every organisation, computed from
the platform's own NGFS "illustrative" carbon prices and sector stranding tiers — and from any organisation's private
emissions row for the issuer. Transition risk is now computed at read time for the reading organisation, on its stated
carbon price and stranded share (E69). Reversible: the table is kept, renamed, and the downgrade restores its name.

Revision ID: transition_stated_20260930
Revises: calc_stated_method_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "transition_stated_20260930"
down_revision: Union[str, None] = "calc_stated_method_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE issuer_transition_scores RENAME TO issuer_transition_scores_retired_20260930")


def downgrade() -> None:
    op.execute("ALTER TABLE issuer_transition_scores_retired_20260930 RENAME TO issuer_transition_scores")
