"""Outbound webhooks — forward Tellumen events to a customer's own systems.

Completes the "output" node's third mode (after download and API pull): direct push. A customer registers an
endpoint URL + the events they care about; when one fires (a governed publish/release, a frozen filing),
Tellumen POSTs a signed JSON payload to their system. Every attempt is recorded in a delivery ledger.

  * webhook_endpoints  — the subscriptions (url, signing secret, event filter), org-scoped + attributed.
  * webhook_deliveries — the ledger: what was sent where, the response, and whether it succeeded.

Revision ID: webhooks_202608
Revises: ingest_tokens_202608
"""
from alembic import op

revision = "webhooks_202608"
down_revision = "ingest_tokens_202608"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS webhook_endpoints (
    endpoint_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    created_by_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    name               TEXT NOT NULL,
    url                TEXT NOT NULL,
    secret             TEXT NOT NULL,                 -- whsec_… ; HMAC key for the signature header
    events             TEXT[] NOT NULL DEFAULT '{}',  -- empty = every event
    is_active          BOOLEAN NOT NULL DEFAULT true,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_delivery_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_webhook_endpoints_org ON webhook_endpoints (org_id);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    delivery_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    endpoint_id  UUID REFERENCES webhook_endpoints(endpoint_id) ON DELETE CASCADE,
    event_type   VARCHAR(60) NOT NULL,
    payload      JSONB,
    status       VARCHAR(12) NOT NULL CHECK (status IN ('delivered','failed')),
    http_status  INTEGER,
    error        TEXT,
    attempts     INTEGER NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_org_time ON webhook_deliveries (org_id, created_at DESC);
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webhook_deliveries")
    op.execute("DROP TABLE IF EXISTS webhook_endpoints")
