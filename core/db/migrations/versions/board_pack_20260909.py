"""Board climate-risk pack — a periodic, immutable, hashed pack the board reviews and named members attest to
under step-up authentication.

Revision ID: board_pack_20260909
Revises: sup_remittance_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "board_pack_20260909"
down_revision: Union[str, None] = "sup_remittance_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERM = ("board.attest", "Attest a board climate-risk pack as a named board or committee member")
GRANT_ROLES = ("admin", "analyst", "approver")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS board_pack (
            pack_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            version       INTEGER NOT NULL,
            period_from   DATE NOT NULL,
            period_to     DATE NOT NULL,
            basis         JSONB NOT NULL,
            content       JSONB NOT NULL,
            sha256        TEXT NOT NULL,
            note          TEXT,
            generated_by  UUID REFERENCES users(user_id),
            generated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (org_id, version)
        );
        CREATE TABLE IF NOT EXISTS board_pack_attestation (
            attestation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pack_id        UUID NOT NULL REFERENCES board_pack(pack_id) ON DELETE CASCADE,
            user_id        UUID NOT NULL REFERENCES users(user_id),
            capacity       TEXT NOT NULL,             -- the capacity in which the person attests (e.g. Chair, Risk Committee)
            statement      TEXT NOT NULL,             -- reviewed | reviewed_with_reservations
            comment        TEXT,
            sha256         TEXT NOT NULL,             -- the content hash the person attested to
            step_up        BOOLEAN NOT NULL DEFAULT TRUE,
            ip             TEXT,
            attested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (pack_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS ix_board_pack_org ON board_pack (org_id, version DESC);
    """)
    op.execute(f"INSERT INTO permissions (code, description) VALUES ('{PERM[0]}', '{PERM[1]}') ON CONFLICT (code) DO NOTHING")
    roles = ", ".join(f"'{r}'" for r in GRANT_ROLES)
    op.execute(f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id FROM roles r JOIN organizations o ON o.org_id = r.org_id, permissions p
        WHERE o.type <> 'regulator' AND r.name IN ({roles}) AND p.code = '{PERM[0]}'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS board_pack_attestation; DROP TABLE IF EXISTS board_pack;")
    op.execute(f"DELETE FROM role_permissions WHERE permission_id IN (SELECT permission_id FROM permissions WHERE code='{PERM[0]}')")
    op.execute(f"DELETE FROM permissions WHERE code = '{PERM[0]}'")
