"""A reporting period's label is derived from its end — enforced on filings, obligations and supervisory deadlines.

Every period here is a financial year, labelled 'FY' + the year of its end (services.governance.filings.period_label).
A supervisory deadline once took a free-text '2026-Q3' and turned it into an annual period ending 31 December still
labelled as a quarter; 41 obligations inherited the label (found in the 2026-09-29 walkthrough). The labels are
corrected here, and a CHECK keeps label and period end one fact from now on.

Revision ID: period_label_derived_20260929
Revises: provided_period_20260929
"""
from typing import Sequence, Union

from alembic import op

revision: str = "period_label_derived_20260929"
down_revision: Union[str, None] = "provided_period_20260929"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (("regulatory_filing", "ck_filing_period_label"),
           ("regulatory_obligation", "ck_obligation_period_label"),
           ("supervision_deadline", "ck_deadline_period_label"))
_DERIVED = "'FY' || EXTRACT(YEAR FROM period_end)::int"


def upgrade() -> None:
    for table, check in _TABLES:
        # a data correction: the label is restated from the period end it always meant
        op.execute(f"UPDATE {table} SET period_label = {_DERIVED} WHERE period_label IS DISTINCT FROM {_DERIVED}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {check} CHECK (period_label = {_DERIVED})")


def downgrade() -> None:
    # removes the rule; the corrected labels stay corrected (the old ones were wrong, not a prior shape to restore)
    for table, check in _TABLES:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {check}")
