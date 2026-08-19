"""Reporting entities — the generic entity an analyst scopes their work to.

An org can contain several reporting entities the analyst switches between, and each located asset can
belong to one. `kind` is a free label so the SAME mechanism serves a legal entity / subsidiary, a fund or
portfolio, a client entity (when the org is a service provider), or a future category — Gaurav: "it could
be 1, 2 or 3 - any of those. maybe a new category in the future as well". Nullable everywhere: an
unassigned asset belongs to the whole org (the implicit "All entities" scope).

Revision ID: reporting_entities_202608
Revises: frost_baseline_202608
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "reporting_entities_202608"
down_revision = "frost_baseline_202608"
branch_labels = None
depends_on = None

_ASSET_TABLES = ["bank_assets", "insurance_policies", "assetmgmt_holdings",
                 "realestate_properties", "sc_company_sites", "sc_sourcing_plots"]


def upgrade():
    op.create_table(
        "reporting_entities",
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False, server_default="legal_entity"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_reporting_entities_org", "reporting_entities", ["org_id"])
    for t in _ASSET_TABLES:
        op.add_column(t, sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index(f"ix_{t}_entity_id", t, ["entity_id"])


def downgrade():
    for t in _ASSET_TABLES:
        op.drop_index(f"ix_{t}_entity_id", table_name=t)
        op.drop_column(t, "entity_id")
    op.drop_index("ix_reporting_entities_org", table_name="reporting_entities")
    op.drop_table("reporting_entities")
