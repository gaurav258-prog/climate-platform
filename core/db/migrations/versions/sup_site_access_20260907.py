"""supervision_scope: entity-granted SITE-LEVEL access for its regulator.

Filings give a supervisor regional aggregates (NUTS-3 / CRESTA); individual site coordinates are the supervised
entity's own data. The entity may open them to its regulator (a review, an inspection, the SupTech lens) and may
revoke. The grant is recorded on the scope row itself and audited on both sides.

Revision ID: sup_site_access_20260907
Revises: ext_ins_cresta_zone_20260906
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_site_access_20260907"
down_revision: Union[str, None] = "ext_ins_cresta_zone_20260906"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE supervision_scope
            ADD COLUMN IF NOT EXISTS site_access_granted_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS site_access_granted_by UUID,
            ADD COLUMN IF NOT EXISTS site_access_revoked_at TIMESTAMPTZ
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE supervision_scope
            DROP COLUMN IF EXISTS site_access_granted_at,
            DROP COLUMN IF EXISTS site_access_granted_by,
            DROP COLUMN IF EXISTS site_access_revoked_at
    """)
