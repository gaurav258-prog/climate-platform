"""A provided value can belong to one reporting entity.

Solvency II states own funds, the SCR, the reinsurance in force and the nat-cat premiums per undertaking and, separately,
for the group (Directive 2009/138/EC Arts 100, 218 ff.; Del. Reg. 2015/35 Art. 335): a subsidiary's solo filing must
use its own figures, never its group's. provided_datapoint.reporting_entity_id names the entity a value is stated for;
NULL = the organisation as a whole (every value held before this migration, unchanged in meaning).

Revision ID: provided_entity_20260930
Revises: due_rules_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "provided_entity_20260930"
down_revision: Union[str, None] = "due_rules_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee4', 'refusal probe', 'insurer', 'DE');
                INSERT INTO reporting_entities (entity_id, org_id, name, kind) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee5', '0bbe0bbe-0000-4000-8000-00000000fee4', 'probe', 'legal_entity');
                INSERT INTO provided_datapoint (org_id, framework, datapoint_key, value_num, source, status, reporting_period_end, reporting_entity_id)
                VALUES ('0bbe0bbe-0000-4000-8000-00000000fee4', 'insurer_solvency', 'scr_total', 1, 'client', 'pending', '2025-12-31', '0bbe0bbe-0000-4000-8000-00000000fee5');""",
    "cleanup": """DELETE FROM provided_datapoint WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee4';
                  DELETE FROM reporting_entities WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee4';
                  DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee4';""",
}


def upgrade() -> None:
    op.execute("""ALTER TABLE provided_datapoint ADD COLUMN reporting_entity_id UUID
                  REFERENCES reporting_entities(entity_id) ON DELETE RESTRICT""")
    op.execute("CREATE INDEX ix_provided_datapoint_entity ON provided_datapoint (org_id, framework, reporting_entity_id)")
    # one live value per datapoint, period AND entity (the organisation's own = no entity)
    op.execute("DROP INDEX ux_provided_live")
    op.execute("""CREATE UNIQUE INDEX ux_provided_live ON provided_datapoint (org_id, framework, datapoint_key,
                  COALESCE(reporting_period_end, '0001-01-01'::date),
                  COALESCE(reporting_entity_id, '00000000-0000-0000-0000-000000000000'::uuid))
                  WHERE status IN ('pending', 'attested')""")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM provided_datapoint WHERE reporting_entity_id IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade provided_entity_20260930: values are stated for a reporting entity, '
                                'which the previous schema cannot tell from the organisation''s own';
            END IF;
        END $$;
    """)
    op.execute("DROP INDEX ux_provided_live")
    op.execute("""CREATE UNIQUE INDEX ux_provided_live ON provided_datapoint (org_id, framework, datapoint_key,
                  COALESCE(reporting_period_end, '0001-01-01'::date)) WHERE status IN ('pending', 'attested')""")
    op.execute("DROP INDEX IF EXISTS ix_provided_datapoint_entity")
    op.execute("ALTER TABLE provided_datapoint DROP COLUMN reporting_entity_id")
