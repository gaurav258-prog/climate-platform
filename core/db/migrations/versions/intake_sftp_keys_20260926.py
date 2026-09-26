"""SFTP access keys for drop-folder channels: an organisation's admins register the public keys their systems log in
with; the SFTP server (go-live #13) is configured from these (one login per organisation, keys only, chrooted to its
drop folders). Keys are revoked, never deleted — the audit trail keeps who added and removed each.

Revision ID: intake_sftp_keys_20260926
Revises: ref_countries_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "intake_sftp_keys_20260926"
down_revision: Union[str, None] = "ref_countries_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_sftp_keys (
            key_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        UUID NOT NULL REFERENCES organizations(org_id),
            label         TEXT NOT NULL,
            key_type      TEXT NOT NULL,
            public_key    TEXT NOT NULL,
            fingerprint   TEXT NOT NULL,
            bits          INTEGER,
            created_by    UUID REFERENCES users(user_id),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at    TIMESTAMPTZ,
            revoked_by    UUID REFERENCES users(user_id),
            CONSTRAINT ck_sftp_key_revoked CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_sftp_key_active ON intake_sftp_keys (fingerprint) WHERE revoked_at IS NULL")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS intake_sftp_keys")
