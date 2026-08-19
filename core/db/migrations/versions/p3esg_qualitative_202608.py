"""p3esg_narratives — the institution-level qualitative Pillar 3 ESG disclosures (Tables 1-3 of Annex XXXIX).

Free-format narrative the institution authors in-app (Environmental / Social / Governance risk tables), stored
org-level as JSONB keyed 'table1.a' -> text — same pattern as sfdr_narratives.

Revision ID: p3esg_qualitative_202608
Revises: kri_p3_transition_202608
"""
from alembic import op

revision = "p3esg_qualitative_202608"
down_revision = "kri_p3_transition_202608"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS p3esg_narratives JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS p3esg_narratives")
