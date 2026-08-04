"""Reporting-entity hierarchy + a reporting-entity link on the unified book.

Turns the flat `reporting_entities` list into a tree so a group can consolidate its legal entities (and any
intermediate sub-groups): each entity gains a `parent_entity_id`, the `ownership_pct` its parent holds of it,
and a `consolidation_method` (full / proportional / equity). Separately, the calc engine reads the unified
`portfolio_entities` book — whose `entity_id` is the ASSET's own PK, not the reporting entity — so we add
`reporting_entity_id` there and backfill it from each vertical's raw table (which already carries the
reporting-entity FK). New uploads leave it NULL = "unassigned / whole org", the implicit top scope.

Revision ID: reporting_entities_hier_202608
Revises: reg_changes_20260803
"""
from alembic import op

revision = "reporting_entities_hier_202608"
down_revision = "reg_changes_20260803"
branch_labels = None
depends_on = None

# raw table -> its primary key (which equals portfolio_entities.entity_id)
_RAW_PK = [
    ("bank_assets", "asset_id"), ("insurance_policies", "policy_id"),
    ("assetmgmt_holdings", "holding_id"), ("realestate_properties", "property_id"),
    ("sc_company_sites", "site_id"), ("sc_sourcing_plots", "plot_id"),
]


def upgrade():
    op.execute("""
        ALTER TABLE reporting_entities
            ADD COLUMN IF NOT EXISTS parent_entity_id UUID REFERENCES reporting_entities(entity_id),
            ADD COLUMN IF NOT EXISTS ownership_pct NUMERIC NOT NULL DEFAULT 100,
            ADD COLUMN IF NOT EXISTS consolidation_method TEXT NOT NULL DEFAULT 'full';
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_reporting_entities_parent ON reporting_entities(parent_entity_id)")

    op.execute("ALTER TABLE portfolio_entities ADD COLUMN IF NOT EXISTS reporting_entity_id UUID")
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolio_entities_reporting ON portfolio_entities(reporting_entity_id)")
    # backfill from each vertical's raw table (raw PK = portfolio_entities.entity_id)
    for tbl, pk in _RAW_PK:
        op.execute(f"""
            UPDATE portfolio_entities pe SET reporting_entity_id = t.entity_id
            FROM {tbl} t WHERE t.{pk} = pe.entity_id AND t.entity_id IS NOT NULL
        """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_portfolio_entities_reporting")
    op.execute("ALTER TABLE portfolio_entities DROP COLUMN IF EXISTS reporting_entity_id")
    op.execute("DROP INDEX IF EXISTS ix_reporting_entities_parent")
    op.execute("""
        ALTER TABLE reporting_entities
            DROP COLUMN IF EXISTS consolidation_method,
            DROP COLUMN IF EXISTS ownership_pct,
            DROP COLUMN IF EXISTS parent_entity_id;
    """)
