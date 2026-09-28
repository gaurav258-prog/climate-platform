"""Each reporting entity can carry its own LEI (ISO 17442).

A filing for one legal entity (solo, or a sub-group's consolidation) identifies that entity to the regulator — in the
XBRL the context identifier is the entity's LEI, not the group's. Until now every filing carried the organisation's
LEI. Unique within the organisation.

Revision ID: entity_lei_20260928
Revises: data_confirmations_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "entity_lei_20260928"
down_revision: Union[str, None] = "data_confirmations_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE reporting_entities ADD COLUMN IF NOT EXISTS lei CHAR(20)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_reporting_entities_lei ON reporting_entities (org_id, lei) WHERE lei IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_reporting_entities_lei")
    op.execute("ALTER TABLE reporting_entities DROP COLUMN IF EXISTS lei")
