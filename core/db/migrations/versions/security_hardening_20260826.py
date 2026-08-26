"""P1 security hardening: login lockout, session revocation, SSO enforcement, password reset, MFA backup codes.

Adds the columns and tables behind: brute-force lockout (failed_login_count / locked_until), revocable sessions
(token_version — bumped to invalidate all outstanding JWTs), tenant SSO enforcement (password_login_disabled),
self-service password reset (password_reset), and MFA recovery (mfa_backup_code). Idempotent.

Revision ID: security_hardening_20260826
Revises: sso_saml_20260826
"""
from alembic import op

revision = "security_hardening_20260826"
down_revision = "sso_saml_20260826"
branch_labels = None
depends_on = None

_DDL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count int NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version int NOT NULL DEFAULT 0;

ALTER TABLE tenant_sso_config ADD COLUMN IF NOT EXISTS password_login_disabled boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS password_reset (
  reset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token_hash text NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','used','expired')),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  used_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_password_reset_token ON password_reset(token_hash);

CREATE TABLE IF NOT EXISTS mfa_backup_code (
  code_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  code_hash text NOT NULL,
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_mfa_backup_user ON mfa_backup_code(user_id);
"""


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mfa_backup_code")
    op.execute("DROP TABLE IF EXISTS password_reset")
    op.execute("ALTER TABLE tenant_sso_config DROP COLUMN IF EXISTS password_login_disabled")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS failed_login_count")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS locked_until")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS token_version")
