"""Prior filings — the ESG reports a customer has already filed and had accepted, brought in as their
reported track record. Two tables:

  reported_filing  — one uploaded filed report (the submitted file itself is kept as the record of truth,
                     with a content hash, so only genuinely submitted files ever enter). Draft until the
                     preparer confirms the read figures; one confirmed filing per (org, framework, period).
  reported_figure  — the report broken down into its individual reported lines, each mapped to a canonical
                     datapoint. Append-only; these are reported actuals, kept separate from Tellumen's
                     modelled figures and from customer-provided (Lane 2) values.

Revision ID: reported_filings_202608
Revises: bank_loan_attributes_202608
"""
from alembic import op

revision = "reported_filings_202608"
down_revision = "bank_loan_attributes_202608"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE IF NOT EXISTS reported_filing (
    filing_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES organizations(org_id),
    framework        TEXT NOT NULL,                 -- catalog framework key, e.g. 'bank_p3esg'
    period_label     TEXT NOT NULL,                 -- reporting period, e.g. '2023'
    period_end       DATE,
    entity_name      TEXT,                          -- the reporting entity named in the filing
    file_format      TEXT NOT NULL CHECK (file_format IN ('xbrl','ixbrl','excel','pdf')),
    original_filename TEXT NOT NULL,
    file_bytes       BYTEA NOT NULL,                -- the original submitted file, retained as the record
    file_sha256      TEXT NOT NULL,                 -- integrity hash of the submitted file
    file_size        INTEGER,
    basis_note       TEXT,                          -- preparation basis for this period (methodology, boundary)
    status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','confirmed')),
    n_lines          INTEGER,                       -- lines read from the report
    uploaded_by      UUID REFERENCES users(user_id),
    uploaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_by     UUID REFERENCES users(user_id),
    confirmed_at     TIMESTAMPTZ
);
-- one confirmed filing per (org, framework, period) — the record for that year
CREATE UNIQUE INDEX IF NOT EXISTS ux_reported_filing_confirmed
    ON reported_filing(org_id, framework, period_label) WHERE status = 'confirmed';
CREATE INDEX IF NOT EXISTS ix_reported_filing_org ON reported_filing(org_id, framework);

CREATE TABLE IF NOT EXISTS reported_figure (
    figure_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id        UUID NOT NULL REFERENCES reported_filing(filing_id) ON DELETE CASCADE,
    org_id           UUID NOT NULL REFERENCES organizations(org_id),
    framework        TEXT NOT NULL,
    period_label     TEXT NOT NULL,
    template_ref     TEXT,                          -- where it sits in the report, e.g. 'Template 5 · Energy · >20y'
    datapoint_key    TEXT,                          -- canonical datapoint it maps to (NULL if unmapped)
    label            TEXT NOT NULL,                 -- the line label as read from the report
    value_num        DOUBLE PRECISION,
    value_text       TEXT,
    unit             TEXT,
    read_method      TEXT NOT NULL DEFAULT 'auto' CHECK (read_method IN ('auto','confirmed')),
    confirmed        BOOLEAN NOT NULL DEFAULT false,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_reported_figure_filing ON reported_figure(filing_id);
CREATE INDEX IF NOT EXISTS ix_reported_figure_series
    ON reported_figure(org_id, framework, datapoint_key, period_label);
"""

DOWN = """
DROP TABLE IF EXISTS reported_figure;
DROP TABLE IF EXISTS reported_filing;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
