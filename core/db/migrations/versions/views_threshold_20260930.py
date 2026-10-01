"""Saved analytics views: the 'highplus' threshold (the platform's High + Very-high score bands, which stood for 'at
risk') becomes 'stated' — at or above the institution's own stated at-risk level (method.at_risk_level, E69). The
'severe' option (the Very-high band) is unchanged. Reversible.

Revision ID: views_threshold_20260930
Revises: transition_stated_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "views_threshold_20260930"
down_revision: Union[str, None] = "transition_stated_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _swap(old: str, new: str) -> None:
    op.execute(f"""
        UPDATE analytics_saved_view SET config = jsonb_set(config, '{{threshold}}', '"{new}"')
        WHERE config ->> 'threshold' = '{old}'
    """)


def upgrade() -> None:
    _swap("highplus", "stated")


def downgrade() -> None:
    _swap("stated", "highplus")
