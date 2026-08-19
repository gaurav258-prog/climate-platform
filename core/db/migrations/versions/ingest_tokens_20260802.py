"""Tenant ingest tokens — service-account credentials for direct source-system integration.

Completes the "input" node of the customer lifecycle with its third mode (after manual entry and template
upload): a direct API pull from the customer's own systems. A token is a TENANT service account —
org-scoped and attributed to the admin who created it — distinct from the legacy customer-scoped api_keys
(which belong to the old scores API) and from user session JWTs.

Format: tlm_live_<48hex>, stored only as SHA-256. The raw token is shown exactly once, at creation.

Revision ID: ingest_tokens_202608
Revises: svc_req_thread_202608
"""
from alembic import op

revision = "ingest_tokens_202608"
down_revision = "svc_req_thread_202608"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS ingest_tokens (
    token_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    created_by_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    name               TEXT NOT NULL,
    token_hash         TEXT NOT NULL UNIQUE,
    token_prefix       VARCHAR(16) NOT NULL,
    is_active          BOOLEAN NOT NULL DEFAULT true,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at       TIMESTAMPTZ,
    expires_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_ingest_tokens_org  ON ingest_tokens (org_id);
CREATE INDEX IF NOT EXISTS ix_ingest_tokens_hash ON ingest_tokens (token_hash);
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingest_tokens")
