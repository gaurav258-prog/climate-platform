"""Solo-and-consolidated as parallel, explicit filing obligations — the foundational fix for the most
severe finding in the 2026-09-23 independent consolidation-scope review.

CRR Art 6 requires most bank subsidiaries to file BOTH an individual (solo) return AND be captured in the
parent's consolidated return — as PARALLEL obligations, not alternatives, waivable only under specific
Art 7 conditions (parent guarantee, prudent-management sign-off, no impediment to fund transfer). Solvency
II Title III draws the same solo-vs-group line. Before this migration, `regulatory_filing`/
`regulatory_obligation` already technically allowed a distinct row per (org, framework, period, entity_id)
— the storage wasn't the blocker — but nothing ever STAMPED which role a filing plays (solo vs consolidated
vs whole-org), nothing recorded whether an entity's individual-reporting duty had actually been waived
(the CRR-safe default is that it has NOT), and `ensure_obligations()` never generated a per-entity solo
obligation at all — only ever one blanket whole-org row. This migration adds the columns; the code that
uses them lands in the same commit.

Revision ID: solo_consolidated_20260923
Revises: entity_structure_import_20260923
"""
import sqlalchemy as sa
from alembic import op

revision = "solo_consolidated_20260923"
down_revision = "entity_structure_import_20260923"
branch_labels = None
depends_on = None


def upgrade():
    # The CRR-safe default: assume an entity's individual-reporting duty is NOT waived unless a customer
    # explicitly records why (solo_waiver_reason) — never silently assume a waiver just because a group
    # filing exists. True for every existing entity too (server_default), since staying silent about a
    # real obligation is the unsafe direction, not the safe one.
    op.add_column("reporting_entities", sa.Column("requires_solo_filing", sa.Boolean, nullable=False,
                                                   server_default=sa.true()))
    op.add_column("reporting_entities", sa.Column("solo_waiver_reason", sa.Text, nullable=True))

    # Explicit, queryable, stamped at generation time — no longer inferred by a reader from which entity_id
    # happened to be picked. NULL for filings created before this migration (never backfilled with a guess).
    op.add_column("regulatory_filing", sa.Column("filing_role", sa.Text, nullable=True))
    op.execute("ALTER TABLE regulatory_filing ADD CONSTRAINT ck_reg_filing_role "
              "CHECK (filing_role IS NULL OR filing_role IN ('solo', 'consolidated', 'whole_org'))")
    op.create_index("ix_reg_filing_role", "regulatory_filing", ["org_id", "framework", "filing_role"])

    # Same explicit tag on the obligation itself, so the calendar can show "solo — Acme Poland S.A." next
    # to "consolidated — whole group" as two distinct, separately-due rows rather than one blanket entry.
    op.add_column("regulatory_obligation", sa.Column("filing_role", sa.Text, nullable=True))
    op.execute("ALTER TABLE regulatory_obligation ADD CONSTRAINT ck_reg_obligation_role "
              "CHECK (filing_role IS NULL OR filing_role IN ('solo', 'consolidated', 'whole_org'))")


def downgrade():
    op.execute("ALTER TABLE regulatory_obligation DROP CONSTRAINT IF EXISTS ck_reg_obligation_role")
    op.drop_column("regulatory_obligation", "filing_role")
    op.drop_index("ix_reg_filing_role", table_name="regulatory_filing")
    op.execute("ALTER TABLE regulatory_filing DROP CONSTRAINT IF EXISTS ck_reg_filing_role")
    op.drop_column("regulatory_filing", "filing_role")
    op.drop_column("reporting_entities", "solo_waiver_reason")
    op.drop_column("reporting_entities", "requires_solo_filing")
