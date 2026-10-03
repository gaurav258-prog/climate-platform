"""A counterparty's revenue, stated once for the counterparty (Pillar 3 Template 1 column i, the revenue-based sector
average; E133).

Annex XL, Template 1, column i: 'Institutions shall base the estimation of scope 3 emissions on the information on
emissions gathered from their counterparties and on the information on sector-average emissions intensity.' A
sector-average intensity per EUR million of revenue needs the counterparty's revenue — a fact of the COUNTERPARTY, so one
counterparty carries one figure, stated through the governed intake (template bank_counterparties) with the end of the
financial year it is for (the row's book date: a flow, converted at the average rate of the twelve months to it) and
where the amount came from (money_source, merged like every converted field).

  bank_counterparties + revenue_eur          the counterparty's revenue for the financial year ending on
                      + revenue_period_end   revenue_period_end (both or neither)

ext_banking.annual_revenue_eur (written only by the demo seed scripts, no date or source) is not moved: it stays the
figure of an exposure that names no counterparty; for an exposure that names one, the counterparty's figure is the one
read (api/routers/bank.py). Downgrade refuses while a counterparty states a revenue (no column would keep it).

Revision ID: p3_t1_revenue_20261002
Revises: prior_undertaking_20261002
"""
from typing import Sequence, Union

from alembic import op

revision: str = "p3_t1_revenue_20261002"
down_revision: Union[str, None] = "prior_undertaking_20261002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROBE_ORG = "0bbe0bbe-0000-4000-8000-00000000fe33"
# A counterparty stating its revenue: the downgrade has no column to keep it, so it must refuse
# (scripts/check_migration_roundtrip.py plants this and requires the refusal).
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_PROBE_ORG}', 'refusal probe', 'bank', 'DE');
                 INSERT INTO bank_counterparties (org_id, counterparty_ref, revenue_eur, revenue_period_end)
                 VALUES ('{_PROBE_ORG}', 'PROBE-REV', 5000000, '2025-12-31');""",
    "cleanup": f"""DELETE FROM bank_counterparties WHERE org_id = '{_PROBE_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_PROBE_ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE bank_counterparties ADD COLUMN revenue_eur NUMERIC(20,2), ADD COLUMN revenue_period_end DATE;
        ALTER TABLE bank_counterparties ADD CONSTRAINT ck_bank_cp_revenue
            CHECK (revenue_eur IS NULL AND revenue_period_end IS NULL
                   OR revenue_eur > 0 AND revenue_period_end IS NOT NULL);
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM bank_counterparties WHERE revenue_eur IS NOT NULL) THEN
            RAISE EXCEPTION 'p3_t1_revenue_20261002 downgrade: counterparties state a revenue — no column before this '
                            'revision keeps it; remove the statements first';
          END IF;
        END $$;
        ALTER TABLE bank_counterparties DROP CONSTRAINT ck_bank_cp_revenue,
                                        DROP COLUMN revenue_period_end, DROP COLUMN revenue_eur;
    """)
