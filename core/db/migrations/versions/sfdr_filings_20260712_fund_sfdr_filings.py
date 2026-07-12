"""fund_sfdr_filings — frozen SFDR statement snapshots for year-on-year comparison

Revision ID: sfdr_filings_20260712
Revises: filing_identity_20260712
Create Date: 2026-07-12

SFDR requires, from the second reference period onward, each PAI indicator to be
shown against the PREVIOUS period's figure. That must be what was ACTUALLY FILED
last year — not last year recomputed from today's data (holdings move, issuers
restate, our data improves). So a filing must be FROZEN when made.

This mirrors bank_disclosure_submissions (the banking vertical's immutable
snapshot) for the fund/SFDR side: one frozen statement per fund per reference
year. Next year's statement reads the prior year's snapshot to build the
comparison column.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sfdr_filings_20260712"
down_revision: Union[str, None] = "filing_identity_20260712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE fund_sfdr_filings (
    filing_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fund_id           UUID NOT NULL REFERENCES funds(fund_id) ON DELETE CASCADE,
    org_id            UUID REFERENCES organizations(org_id) ON DELETE SET NULL,
    reference_year    INTEGER NOT NULL,
    period_start      DATE,
    period_end        DATE,
    statement         JSONB NOT NULL,               -- the frozen statement snapshot
    narrative_summary TEXT,
    filed_by          VARCHAR(200),
    filed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    status            VARCHAR(12) NOT NULL DEFAULT 'filed'
                      CHECK (status IN ('filed','superseded')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (fund_id, reference_year)               -- one official filing per fund per year
);
CREATE INDEX ix_sfdr_filings_fund_year ON fund_sfdr_filings(fund_id, reference_year DESC);
"""

DOWNGRADE = "DROP TABLE IF EXISTS fund_sfdr_filings;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
