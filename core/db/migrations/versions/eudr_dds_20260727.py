"""EUDR Due Diligence Statement — operator identity + immutable filing record.

Phase 2 Tier 1. To assemble a DDS the operator block needs an EORI number and a registered
address (we already hold legal_name/LEI/country). And a filed DDS is a legal record, so it gets
its own immutable table (mirrors fund_sfdr_filings): the assembled payload is frozen, and the
TRACES reference/verification numbers the operator gets back on submission are captured here.

Revision ID: eudr_dds_20260727
Revises: eudr_determination_20260727
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "eudr_dds_20260727"
down_revision = "eudr_determination_20260727"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("eori", sa.String(), nullable=True))
    op.add_column("organizations", sa.Column("operator_address", sa.String(), nullable=True))
    op.create_table(
        "sc_eudr_dds",
        sa.Column("dds_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False, index=True),
        # draft -> ready (no blockers) -> filed (TRACES reference captured)
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("reference_number", sa.String(), nullable=True),      # TRACES DDS reference
        sa.Column("verification_number", sa.String(), nullable=True),   # TRACES verification
        sa.Column("payload", JSONB, nullable=False),                    # the assembled DDS (frozen)
        sa.Column("blockers", JSONB, nullable=True),                    # plots preventing a filing
        sa.Column("plot_count", sa.Integer, nullable=True),
        sa.Column("covered_count", sa.Integer, nullable=True),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reference_captured_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sc_eudr_dds")
    op.drop_column("organizations", "operator_address")
    op.drop_column("organizations", "eori")
