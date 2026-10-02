"""An EUDR due diligence statement is named and dated by its shipment (E108): it has no reporting period, so its label
is '<shipment reference> · <shipment date>' rather than 'FY<year>'. The label rule stays checkable by the database: a
statement's label ends with its own date (period_end); every other filing keeps 'FY' || year. Statements prepared before
this rule are relabelled from their shipment (the label is derived, so the downgrade relabels them back exactly).

Revision ID: eudr_label_20261001
Revises: worker_jobs_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "eudr_label_20261001"
down_revision: Union[str, None] = "worker_jobs_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE regulatory_filing DROP CONSTRAINT ck_filing_period_label;
        UPDATE regulatory_filing f SET period_label = COALESCE(m.external_ref, 'shipment') || ' · ' || f.period_end::text
          FROM eudr_movement m WHERE m.movement_id = f.eudr_movement_id AND f.framework = 'eudr_dds';
        ALTER TABLE regulatory_filing ADD CONSTRAINT ck_filing_period_label CHECK (
            CASE WHEN framework = 'eudr_dds' THEN period_label LIKE '% · ' || period_end::text
                 ELSE period_label = ('FY'::text || (EXTRACT(year FROM period_end))::integer) END);
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE regulatory_filing DROP CONSTRAINT ck_filing_period_label;
        UPDATE regulatory_filing SET period_label = 'FY' || (EXTRACT(year FROM period_end))::integer WHERE framework = 'eudr_dds';
        ALTER TABLE regulatory_filing ADD CONSTRAINT ck_filing_period_label
            CHECK ((period_label = ('FY'::text || (EXTRACT(year FROM period_end))::integer)));
    """)
