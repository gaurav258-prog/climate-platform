"""NULL-safe uniqueness for regulatory_obligation, and de-dup any rows a NULL-distinct UNIQUE let through.

The table's UNIQUE(org_id, framework, period_end, entity_id) does not dedupe org-level obligations because
Postgres treats NULL entity_id as distinct — so repeated ensure_obligations() calls inserted duplicates.
This replaces it with a COALESCE-based partial unique index (same trick used for regulatory_filing) and
collapses any existing duplicates to the earliest row.

Revision ID: reg_obligation_uniq_20260803
Revises: reg_filing_guard_fix_20260803
"""
from alembic import op

revision = "reg_obligation_uniq_20260803"
down_revision = "reg_filing_guard_fix_20260803"
branch_labels = None
depends_on = None

ZERO = "'00000000-0000-0000-0000-000000000000'::uuid"


def upgrade() -> None:
    # keep the earliest obligation per logical key, delete the rest
    op.execute(f"""
        DELETE FROM regulatory_obligation ro USING (
            SELECT org_id, framework, period_end, COALESCE(entity_id, {ZERO}) AS ek,
                   MIN(created_at) AS keep_at
            FROM regulatory_obligation
            GROUP BY org_id, framework, period_end, COALESCE(entity_id, {ZERO})
            HAVING COUNT(*) > 1
        ) dup
        WHERE ro.org_id = dup.org_id AND ro.framework = dup.framework
          AND ro.period_end = dup.period_end
          AND COALESCE(ro.entity_id, {ZERO}) = dup.ek
          AND ro.created_at <> dup.keep_at
    """)
    op.execute("ALTER TABLE regulatory_obligation DROP CONSTRAINT IF EXISTS regulatory_obligation_org_id_framework_period_end_entity_id_key")
    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_reg_obligation_key
        ON regulatory_obligation (org_id, framework, period_end, COALESCE(entity_id, {ZERO}))
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_reg_obligation_key")
