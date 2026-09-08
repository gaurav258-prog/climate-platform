"""supervision_scope lifecycle: who added / ended the supervision, and the entity's acknowledgement.

Revision ID: sup_scope_ack_20260908
Revises: sup_requests_20260907
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_scope_ack_20260908"
down_revision: Union[str, None] = "sup_requests_20260907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE supervision_scope
            ADD COLUMN IF NOT EXISTS added_by         UUID,
            ADD COLUMN IF NOT EXISTS ended_at         TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS ended_by         UUID,
            ADD COLUMN IF NOT EXISTS acknowledged_at  TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS acknowledged_by  UUID
    """)
    op.execute("INSERT INTO permissions (code, description) VALUES ('supervisor.scope.manage', "
               "'Add and end the entities this authority supervises') ON CONFLICT (code) DO NOTHING")


def downgrade() -> None:
    op.execute("""ALTER TABLE supervision_scope DROP COLUMN IF EXISTS added_by, DROP COLUMN IF EXISTS ended_at,
                  DROP COLUMN IF EXISTS ended_by, DROP COLUMN IF EXISTS acknowledged_at, DROP COLUMN IF EXISTS acknowledged_by""")
