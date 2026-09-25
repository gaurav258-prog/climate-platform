"""ingest_batches: the ledger of every customer data batch — what arrived, what the controls found, who signed off.

One row per import attempt that reached the gate: file identity (name + sha256, so a repeat file is caught),
what the customer declared they sent, the receipt / transformation / gate / landing control results, and the named
person who signed off a gated batch (with their reason). Nothing here changes what the engine computes; it is
the audit trail that lets anyone answer "where did this book come from, and was it checked?".

Revision ID: ingest_batches_20260925
Revises: consolidation_basis_20260923
"""
from typing import Sequence, Union

from alembic import op

revision: str = "ingest_batches_20260925"
down_revision: Union[str, None] = "consolidation_basis_20260923"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ingest_batches (
            batch_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            template        TEXT NOT NULL,
            via             TEXT NOT NULL DEFAULT 'upload',
            filename        TEXT,
            sha256          TEXT NOT NULL,
            received_by     UUID,
            received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            declared        JSONB NOT NULL DEFAULT '{}'::jsonb,
            n_total         INTEGER NOT NULL,
            n_valid         INTEGER NOT NULL,
            n_rejected      INTEGER NOT NULL,
            value_field     TEXT,
            value_valid     DOUBLE PRECISION,
            receipt         JSONB NOT NULL,
            transform       JSONB NOT NULL,
            gate_status     TEXT NOT NULL,
            gate_reasons    JSONB NOT NULL DEFAULT '[]'::jsonb,
            signoff_by      UUID,
            signoff_reason  TEXT,
            status          TEXT NOT NULL DEFAULT 'accepted',
            landing         JSONB,
            imported_at     TIMESTAMPTZ,
            CONSTRAINT ck_ingest_batch_status CHECK (status IN ('accepted', 'imported')),
            CONSTRAINT ck_ingest_batch_gate CHECK (gate_status IN ('pass', 'needs_signoff')),
            CONSTRAINT ck_ingest_batch_signoff CHECK (gate_status = 'pass' OR (signoff_by IS NOT NULL AND length(btrim(signoff_reason)) >= 10))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ingest_batches_org ON ingest_batches (org_id, received_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ingest_batches_sha ON ingest_batches (org_id, template, sha256)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingest_batches")
