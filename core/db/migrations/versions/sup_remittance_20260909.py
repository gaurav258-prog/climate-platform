"""Governed remittance — an evidence pack shared onward to another authority, college or committee: scoped,
time-limited, watermarked, revocable, audited on both sides, with a download log.

Revision ID: sup_remittance_20260909
Revises: sup_transmission_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_remittance_20260909"
down_revision: Union[str, None] = "sup_transmission_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERM = ("supervisor.remit", "Remit an evidence pack to another authority, college or committee under a governed share")
GRANT_ROLES = ("inspector", "head", "admin")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervision_remittance (
            remittance_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regulator_org_id  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            supervised_org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            pack_id           UUID NOT NULL REFERENCES supervision_evidence_pack(pack_id) ON DELETE CASCADE,
            reference         TEXT NOT NULL,
            recipient_kind    TEXT NOT NULL,
            recipient_name    TEXT NOT NULL,
            recipient_org_id  UUID REFERENCES organizations(org_id) ON DELETE SET NULL,   -- set when the recipient is on Tellumen
            recipient_email   TEXT,
            purpose           TEXT NOT NULL,
            legal_basis       JSONB NOT NULL,
            sections          JSONB NOT NULL,          -- the pack sections included; the rest are withheld
            content           JSONB NOT NULL,          -- the scoped canonical content actually remitted
            content_sha256    TEXT NOT NULL,
            pdf               BYTEA NOT NULL,          -- the watermarked document, fixed at issue
            pdf_sha256        TEXT NOT NULL,
            watermark         TEXT NOT NULL,
            token_hash        TEXT NOT NULL UNIQUE,    -- SHA-256 of the bearer token; the token itself is shown once
            expires_at        TIMESTAMPTZ NOT NULL,
            max_downloads     INTEGER,
            n_downloads       INTEGER NOT NULL DEFAULT 0,
            created_by        UUID REFERENCES users(user_id),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at        TIMESTAMPTZ,
            revoked_by        UUID REFERENCES users(user_id),
            revoke_reason     TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_remittance_regulator ON supervision_remittance (regulator_org_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS ix_remittance_entity    ON supervision_remittance (supervised_org_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS ix_remittance_recipient ON supervision_remittance (recipient_org_id) WHERE recipient_org_id IS NOT NULL;

        CREATE TABLE IF NOT EXISTS supervision_remittance_access (
            access_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            remittance_id UUID NOT NULL REFERENCES supervision_remittance(remittance_id) ON DELETE CASCADE,
            at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            action        TEXT NOT NULL,               -- view | download_pdf | download_json
            outcome       TEXT NOT NULL,               -- ok | expired | revoked | exhausted
            actor_user_id UUID REFERENCES users(user_id),
            actor_org_id  UUID REFERENCES organizations(org_id),
            ip            TEXT,
            user_agent    TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_remittance_access ON supervision_remittance_access (remittance_id, at DESC);
    """)
    op.execute("INSERT INTO permissions (code, description) VALUES "
               f"('{PERM[0]}', '{PERM[1]}') ON CONFLICT (code) DO NOTHING")
    # existing supervisory bodies: the roles that already hold evidence export (plus heads and admins) may remit
    roles = ", ".join(f"'{r}'" for r in GRANT_ROLES)
    op.execute(f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id FROM roles r JOIN organizations o ON o.org_id = r.org_id, permissions p
        WHERE o.type = 'regulator' AND r.name IN ({roles}) AND p.code = '{PERM[0]}'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervision_remittance_access; DROP TABLE IF EXISTS supervision_remittance;")
    op.execute(f"DELETE FROM role_permissions WHERE permission_id IN (SELECT permission_id FROM permissions WHERE code='{PERM[0]}')")
    op.execute(f"DELETE FROM permissions WHERE code = '{PERM[0]}'")
