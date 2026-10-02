"""A prior filing is a filing of one undertaking for one period (E123) — so the figures it reported can be the previous
period's figures ESRS 1 compares with (ESRS 1 §83-84 of 2023/2772; §83-87 of 2026/1563).

  reported_filing  + entity_id: the undertaking the filed report is for (a reporting entity; NULL with undertaking_stated
                     = the organisation itself)
                   + undertaking_stated: whether that was stated — never inferred from the free-text entity name printed
                     on the report (kept as read)
                   + period_end_stated: whether the period end was stated — earlier uploads could leave it blank and the
                     platform then took 31 December of a year read from the label (an assumption, not a fact); rows from
                     before this migration are marked not stated, and a filing whose undertaking or period end is not
                     stated supplies no comparative
  one confirmed filing per undertaking and period: per (organisation, framework, undertaking, period end) once both are
  stated — the earlier rule, one per period label for the whole organisation, kept only for filings not yet stated (two
  undertakings' reports for the same year are two filings; two confirmed reports of one undertaking for one period
  would leave 'the reported figure' undecided)

Revision ID: prior_undertaking_20261002
Revises: p3_t1_counterparty_20261002
"""
from typing import Sequence, Union

from alembic import op

revision: str = "prior_undertaking_20261002"
down_revision: Union[str, None] = "p3_t1_counterparty_20261002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE reported_filing ADD COLUMN entity_id UUID REFERENCES reporting_entities(entity_id) ON DELETE RESTRICT,
                                    ADD COLUMN undertaking_stated BOOLEAN NOT NULL DEFAULT false,
                                    ADD COLUMN period_end_stated BOOLEAN NOT NULL DEFAULT false;
        ALTER TABLE reported_filing ADD CONSTRAINT ck_reported_filing_undertaking
            CHECK (entity_id IS NULL OR undertaking_stated);
        ALTER TABLE reported_filing ADD CONSTRAINT ck_reported_filing_period_end
            CHECK (NOT period_end_stated OR period_end IS NOT NULL);
        DROP INDEX ux_reported_filing_confirmed;
        CREATE UNIQUE INDEX ux_reported_filing_confirmed ON reported_filing (org_id, framework, period_label)
            WHERE status = 'confirmed' AND NOT (undertaking_stated AND period_end_stated);
        CREATE UNIQUE INDEX ux_reported_filing_undertaking ON reported_filing
            (org_id, framework, COALESCE(entity_id, '00000000-0000-0000-0000-000000000000'::uuid), period_end)
            WHERE status = 'confirmed' AND undertaking_stated AND period_end_stated;
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX ux_reported_filing_undertaking;
        DROP INDEX ux_reported_filing_confirmed;
        CREATE UNIQUE INDEX ux_reported_filing_confirmed ON reported_filing (org_id, framework, period_label)
            WHERE status = 'confirmed';
        ALTER TABLE reported_filing DROP CONSTRAINT ck_reported_filing_period_end,
                                    DROP CONSTRAINT ck_reported_filing_undertaking,
                                    DROP COLUMN period_end_stated, DROP COLUMN undertaking_stated, DROP COLUMN entity_id;
    """)
