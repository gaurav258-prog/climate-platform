"""A provided value carries its currency and, for a breakdown, the member it is for.

An amount an undertaking states (a carrying amount, net revenue, an internal carbon price) is in its own currency: it
is kept as sent (value_num + value_currency), converted to EUR by the money rules (closing rate for a position, the
year's average for a flow — services.intake.money) into value_eur, with the rate in money_source. A figure reported per
member of a breakdown (Scope 3 per GHG Protocol category, real estate per energy-efficiency class) names the member;
one live value per datapoint, period, undertaking and member.

Revision ID: provided_money_20260930
Revises: site_intake_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "provided_money_20260930"
down_revision: Union[str, None] = "site_intake_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROBE_ORG = "0bbe0bbe-0000-4000-8000-00000000fee9"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_PROBE_ORG}', 'refusal probe', 'manufacturer', 'SE');
                 INSERT INTO provided_datapoint (org_id, framework, datapoint_key, value_num, source, reporting_period_end,
                                                 value_currency, value_eur)
                 VALUES ('{_PROBE_ORG}', 'esrs', 'fs.net_revenue', 1000000, 'client', '2025-12-31', 'SEK', 87000);""",
    "cleanup": f"""DELETE FROM provided_datapoint WHERE org_id = '{_PROBE_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_PROBE_ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE provided_datapoint
            ADD COLUMN value_currency CHAR(3), ADD COLUMN value_eur DOUBLE PRECISION, ADD COLUMN money_source JSONB,
            ADD COLUMN breakdown_member TEXT,
            ADD CONSTRAINT ck_provided_currency CHECK (value_currency IS NULL OR value_num IS NOT NULL);
        DROP INDEX ux_provided_live;
        CREATE UNIQUE INDEX ux_provided_live ON provided_datapoint (org_id, framework, datapoint_key,
            COALESCE(reporting_period_end, '0001-01-01'::date),
            COALESCE(reporting_entity_id, '00000000-0000-0000-0000-000000000000'::uuid), COALESCE(breakdown_member, ''))
            WHERE status = ANY (ARRAY['pending'::text, 'attested'::text]);
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM provided_datapoint WHERE value_currency IS NOT NULL OR breakdown_member IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade provided_money_20260930: provided values carry their currency or a '
                                'breakdown member';
            END IF;
        END $$;
    """)
    op.execute("""
        DROP INDEX ux_provided_live;
        CREATE UNIQUE INDEX ux_provided_live ON provided_datapoint (org_id, framework, datapoint_key,
            COALESCE(reporting_period_end, '0001-01-01'::date),
            COALESCE(reporting_entity_id, '00000000-0000-0000-0000-000000000000'::uuid))
            WHERE status = ANY (ARRAY['pending'::text, 'attested'::text]);
        ALTER TABLE provided_datapoint DROP CONSTRAINT ck_provided_currency, DROP COLUMN breakdown_member,
            DROP COLUMN money_source, DROP COLUMN value_eur, DROP COLUMN value_currency;
    """)
