"""Supplied (Lane 2) values belong to a reporting period.

provided_datapoint.reporting_period_end  the period end the value is for. A value supersedes only the earlier value for
                                         the same datapoint AND period, and a filing freezes only the values of its own
                                         period — a figure given for one year never lands in another year's filing.
Backfilled from the free-text period_label where it names a year ('2025', 'FY2025' → 2025-12-31); otherwise left
empty ('period not stated', shown as such and never frozen into a dated filing).

Also: the live-value uniqueness now includes the period.

Revision ID: provided_period_20260929
Revises: bank_gar_facts_20260929
"""
from typing import Sequence, Union

from alembic import op

revision: str = "provided_period_20260929"
down_revision: Union[str, None] = "bank_gar_facts_20260929"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE provided_datapoint ADD COLUMN IF NOT EXISTS reporting_period_end DATE")
    op.execute("""UPDATE provided_datapoint
                  SET reporting_period_end = make_date(CAST(substring(period_label from '(?:^|FY)\\s*(\\d{4})$') AS int), 12, 31)
                  WHERE reporting_period_end IS NULL AND period_label ~ '^(FY)?\\s*\\d{4}$'""")
    op.execute("DROP INDEX IF EXISTS ux_provided_live")
    op.execute("""CREATE UNIQUE INDEX ux_provided_live ON provided_datapoint
                  (org_id, framework, datapoint_key, COALESCE(reporting_period_end, DATE '0001-01-01'))
                  WHERE status IN ('pending', 'attested')""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_provided_live")
    op.execute("""CREATE UNIQUE INDEX ux_provided_live ON provided_datapoint (org_id, framework, datapoint_key)
                  WHERE status IN ('pending', 'attested')""")
    op.execute("ALTER TABLE provided_datapoint DROP COLUMN IF EXISTS reporting_period_end")
