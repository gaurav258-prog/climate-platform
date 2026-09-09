"""filing_transmission — every attempt to deliver a filing to an authority, with its channel, payload hash, status and receipt.

Revision ID: sup_transmission_20260909
Revises: sup_correspondence_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_transmission_20260909"
down_revision: Union[str, None] = "sup_correspondence_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS filing_transmission (
            transmission_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id            UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            filing_id         UUID NOT NULL REFERENCES regulatory_filing(filing_id) ON DELETE CASCADE,
            framework         TEXT NOT NULL,
            period_label      TEXT NOT NULL,
            channel_id        TEXT NOT NULL,
            channel_kind      TEXT NOT NULL,
            format            TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'queued',   -- queued | sent | acknowledged | rejected | failed | awaiting_credentials | awaiting_receipt
            attempts          INTEGER NOT NULL DEFAULT 0,
            payload_sha256    TEXT,
            payload_bytes     INTEGER,
            filename          TEXT,
            recipient_org_id  UUID,                              -- the supervisory body, for the Tellumen channel
            sent_at           TIMESTAMPTZ,
            receipt_ref       TEXT,
            receipt_at        TIMESTAMPTZ,
            receipt_payload   JSONB,
            error             TEXT,
            created_by        UUID,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_filing_transmission_org ON filing_transmission (org_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_filing_transmission_recipient ON filing_transmission (recipient_org_id, created_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS org_channel_credential (
            org_id      UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            channel_id  TEXT NOT NULL,
            key         TEXT NOT NULL,
            value_enc   TEXT NOT NULL,                     -- encrypted at rest (core.security.crypto)
            updated_by  UUID,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (org_id, channel_id, key)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS org_channel_credential")
    op.execute("DROP TABLE IF EXISTS filing_transmission")
