"""GRC follow-ups: appetite version history, governed assurance-pack shares for auditors, the third-party register,
the auditor role's permissions and the appetite approval action.

Revision ID: grc_remaining_20260909
Revises: model_risk_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "grc_remaining_20260909"
down_revision: Union[str, None] = "model_risk_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS kri_threshold_version (
            version_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id              UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            framework           TEXT NOT NULL,
            kri_key             TEXT NOT NULL,
            version             INTEGER NOT NULL,
            amber               NUMERIC,
            red                 NUMERIC,
            direction           TEXT,
            previous            JSONB,
            reason              TEXT,
            changed_by          UUID REFERENCES users(user_id),
            approved_by         UUID REFERENCES users(user_id),
            approval_request_id UUID,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (org_id, framework, kri_key, version)
        );
        CREATE INDEX IF NOT EXISTS ix_kri_threshold_version ON kri_threshold_version (org_id, framework, created_at DESC);

        CREATE TABLE IF NOT EXISTS assurance_share (
            share_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            filing_id       UUID NOT NULL REFERENCES regulatory_filing(filing_id) ON DELETE CASCADE,
            recipient_name  TEXT NOT NULL,
            recipient_email TEXT NOT NULL,
            purpose         TEXT NOT NULL,
            token_hash      TEXT NOT NULL UNIQUE,
            expires_at      TIMESTAMPTZ NOT NULL,
            max_downloads   INTEGER,
            n_downloads     INTEGER NOT NULL DEFAULT 0,
            created_by      UUID REFERENCES users(user_id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at      TIMESTAMPTZ,
            revoked_by      UUID REFERENCES users(user_id)
        );
        CREATE INDEX IF NOT EXISTS ix_assurance_share_filing ON assurance_share (org_id, filing_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS assurance_share_access (
            access_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            share_id   UUID NOT NULL REFERENCES assurance_share(share_id) ON DELETE CASCADE,
            at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            action     TEXT NOT NULL,
            outcome    TEXT NOT NULL,
            ip         TEXT,
            user_agent TEXT
        );

        CREATE TABLE IF NOT EXISTS third_party (
            third_party_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id           UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            kind             TEXT NOT NULL,             -- registry: critical_service_provider | cloud | data_centre | custodian | outsourcer | supplier | other
            service          TEXT,
            criticality      TEXT NOT NULL DEFAULT 'important',   -- critical | important | standard
            address          TEXT,
            country          TEXT,
            latitude         DOUBLE PRECISION NOT NULL,
            longitude        DOUBLE PRECISION NOT NULL,
            h3_cell          TEXT NOT NULL,
            geocode_precision TEXT,
            contract_ref     TEXT,
            note             TEXT,
            active           BOOLEAN NOT NULL DEFAULT TRUE,
            created_by       UUID REFERENCES users(user_id),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            ended_at         TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS ix_third_party_org ON third_party (org_id) WHERE active;
    """)
    # the appetite change becomes a governed action in the approval matrix (off by default, like the other config actions)
    op.execute("""INSERT INTO approval_policy (org_id, action_key, requires_approval, material_fields)
                  SELECT NULL, 'config.kri_appetite', FALSE, '["amber","red","direction"]'::jsonb
                  WHERE NOT EXISTS (SELECT 1 FROM approval_policy WHERE org_id IS NULL AND action_key = 'config.kri_appetite')""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS assurance_share_access; DROP TABLE IF EXISTS assurance_share; DROP TABLE IF EXISTS third_party; DROP TABLE IF EXISTS kri_threshold_version;")
    op.execute("DELETE FROM approval_policy WHERE org_id IS NULL AND action_key = 'config.kri_appetite'")
