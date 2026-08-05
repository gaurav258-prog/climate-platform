"""Cell-level manual overrides on the final form — a separate, audited layer over the immutable snapshot.

A preparer proposes a manual value for one datapoint (by its stable key) with a reason; it stays PENDING
until a second pair of eyes approves it (routed through the existing approval_requests machinery). An approved
override replaces that cell on the effective form — the frozen snapshot is never mutated, and the original
calculated value + who/when/why are preserved. One live (pending|approved) override per (filing, datapoint);
a new proposal supersedes the prior.

Revision ID: filing_cell_override_202608
Revises: reporting_entities_hier_202608
"""
from alembic import op

revision = "filing_cell_override_202608"
down_revision = "reporting_entities_hier_202608"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS filing_cell_override (
    override_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(org_id),
    filing_id           UUID NOT NULL REFERENCES regulatory_filing(filing_id) ON DELETE CASCADE,
    datapoint_key       TEXT NOT NULL,
    original_value      NUMERIC,          -- the calculated value at the moment of proposal (preserved)
    proposed_value      NUMERIC NOT NULL, -- the manual value
    reason              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','approved','rejected','superseded')),
    approval_request_id UUID REFERENCES approval_requests(request_id),
    proposed_by         UUID REFERENCES users(user_id),
    proposed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_by          UUID REFERENCES users(user_id),
    decided_at          TIMESTAMPTZ,
    decision_reason     TEXT
);
CREATE INDEX IF NOT EXISTS ix_fco_filing ON filing_cell_override (filing_id);
CREATE INDEX IF NOT EXISTS ix_fco_live   ON filing_cell_override (filing_id, datapoint_key)
    WHERE status IN ('pending','approved');
"""


def upgrade():
    op.execute(DDL)


def downgrade():
    op.execute("DROP TABLE IF EXISTS filing_cell_override")
