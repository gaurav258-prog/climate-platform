"""supervision_request.responded_at — when the entity first answered (its first status step on the thread).

The SLA metrics on the supervisor's engagement need three real timestamps: sent (issued_at, falling back to
raised_at), acknowledged (receipt_at, the entity's formal receipt) and responded. The first two were recorded;
the response was only implicit in the thread (the entity's first message that moves the status). This adds the
column, back-fills it from that message, and engagement.add_message records it from now on — once, never moved.

Revision ID: requests_sla_20260912
Revises: relevance_model_version_20260912
"""
from typing import Sequence, Union

from alembic import op

revision: str = "requests_sla_20260912"
down_revision: Union[str, None] = "relevance_model_version_20260912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE supervision_request ADD COLUMN IF NOT EXISTS responded_at TIMESTAMPTZ")
    op.execute("""
        UPDATE supervision_request q SET responded_at = m.first_at
        FROM (SELECT request_id, min(created_at) AS first_at FROM supervision_request_message
              WHERE side = 'entity' AND status_to IS NOT NULL GROUP BY request_id) m
        WHERE m.request_id = q.request_id AND q.responded_at IS NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE supervision_request DROP COLUMN IF EXISTS responded_at")
