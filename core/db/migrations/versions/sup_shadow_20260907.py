"""portfolio_entities: provenance for a supervisor's SHADOW book (Tier-2 lens).

A regulator rebuilds a supervised bank's book from the granular data it already holds (AnaCredit-style) so the
same portfolio engine can recompute the bank's template independently. Those rows live on the regulator's own
org in the same table, tagged: source='supervisor_shadow', subject_org_id=<the bank>, location_precision =
how the location was resolved ('point' | 'nuts3' | 'postcode→nuts3' | 'unlocated'), source_ref = intake batch.
Every existing reader keeps default source='own', so shadow rows never appear in an entity's own book.

Revision ID: sup_shadow_20260907
Revises: sup_intake_20260907
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_shadow_20260907"
down_revision: Union[str, None] = "sup_intake_20260907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE portfolio_entities
            ADD COLUMN IF NOT EXISTS source VARCHAR(24) NOT NULL DEFAULT 'own',
            ADD COLUMN IF NOT EXISTS subject_org_id UUID REFERENCES organizations(org_id) ON DELETE CASCADE,
            ADD COLUMN IF NOT EXISTS location_precision VARCHAR(24),
            ADD COLUMN IF NOT EXISTS source_ref TEXT
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pe_shadow ON portfolio_entities (org_id, subject_org_id) WHERE source = 'supervisor_shadow'")
    op.execute("ALTER TABLE portfolio_entities DROP CONSTRAINT IF EXISTS ck_pe_source")
    op.execute("ALTER TABLE portfolio_entities ADD CONSTRAINT ck_pe_source CHECK (source IN ('own', 'supervisor_shadow'))")


def downgrade() -> None:
    op.execute("ALTER TABLE portfolio_entities DROP CONSTRAINT IF EXISTS ck_pe_source")
    op.execute("DROP INDEX IF EXISTS ix_pe_shadow")
    op.execute("""ALTER TABLE portfolio_entities DROP COLUMN IF EXISTS source, DROP COLUMN IF EXISTS subject_org_id,
                  DROP COLUMN IF EXISTS location_precision, DROP COLUMN IF EXISTS source_ref""")
