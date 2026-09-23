"""Entity-structure import — the staging/review model an org tree lands in before it becomes real
reporting_entities rows. Standardizes what was, until now, a one-off hand-written script per customer
(scripts/seed_ing_org_structure.py) into a reusable ingestion path: any source (a customer-filled CSV
today; a document-extraction pipeline once ANTHROPIC_API_KEY is configured — see
services/governance/entity_structure_import.py) writes into this SAME staging shape, a human reviews/edits
it, and only an explicit confirm actually creates entities — never a silent auto-create, regardless of
source. Nothing here bypasses services.governance.entities.create_entity(); confirm_import() calls it.

Revision ID: entity_structure_import_20260923
Revises: ifrs_incurred_region_20260922
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "entity_structure_import_20260923"
down_revision = "ifrs_incurred_region_20260922"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "entity_structure_imports",
        sa.Column("import_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text, nullable=False),                     # 'manual_csv' | 'document_extraction'
        sa.Column("source_document_name", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="staged"),  # staged | confirmed | discarded
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_esi_org", "entity_structure_imports", ["org_id"])

    op.create_table(
        "entity_structure_import_rows",
        sa.Column("row_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        # row_ref/parent_ref resolve parent-child links WITHIN one batch before real entity_ids exist — the
        # natural key is the entity's own name (what a customer's CSV will actually contain), never a
        # synthetic id the uploader would have to invent.
        sa.Column("row_ref", sa.Text, nullable=False),
        sa.Column("parent_ref", sa.Text, nullable=True),
        # alternative to parent_ref: attach under an entity that ALREADY exists in reporting_entities
        # (outside this batch) — e.g. adding a newly-disclosed subsidiary to an already-onboarded tree.
        sa.Column("parent_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False, server_default="legal_entity"),
        sa.Column("country", sa.Text, nullable=True),
        sa.Column("ownership_pct", sa.Numeric, nullable=True),
        sa.Column("consolidation_method", sa.Text, nullable=True),
        # provenance: WHERE this row's data came from — a citation for a document-extracted row (e.g. "Note
        # 41, p.200"), or "customer-entered" for a manual one. Never fabricated, always disclosed.
        sa.Column("source_note", sa.Text, nullable=True),
        # 0-1, extraction confidence — NULL for a manually-entered row (there is no "confidence" to report
        # for a human's own typed input; NULL means "not applicable", never a fabricated 1.0).
        sa.Column("confidence", sa.Numeric, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="proposed"),  # proposed | edited | rejected
        sa.Column("created_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_esir_import", "entity_structure_import_rows", ["import_id"])


def downgrade():
    op.drop_index("ix_esir_import", table_name="entity_structure_import_rows")
    op.drop_table("entity_structure_import_rows")
    op.drop_index("ix_esi_org", table_name="entity_structure_imports")
    op.drop_table("entity_structure_imports")
