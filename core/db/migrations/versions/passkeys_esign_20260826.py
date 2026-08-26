"""P3: WebAuthn passkeys + e-signature requests.

Passkey (FIDO2/WebAuthn) credentials + a short-lived challenge store for the registration/authentication
ceremonies, and an e-signature request record (DocuSign-gated; falls back to upload-into-vault). Idempotent.

Revision ID: passkeys_esign_20260826
Revises: growth_p3_20260826
"""
from alembic import op

revision = "passkeys_esign_20260826"
down_revision = "growth_p3_20260826"
branch_labels = None
depends_on = None

_DDL = """
CREATE TABLE IF NOT EXISTS webauthn_credential (
  credential_id text PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  public_key bytea NOT NULL,
  sign_count bigint NOT NULL DEFAULT 0,
  name text,
  transports text,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_webauthn_cred_user ON webauthn_credential(user_id);

CREATE TABLE IF NOT EXISTS webauthn_challenge (
  ref text PRIMARY KEY,
  challenge text NOT NULL,
  kind varchar(20) NOT NULL,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS esign_request (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  title text NOT NULL,
  signer_email text NOT NULL,
  provider varchar(20) NOT NULL DEFAULT 'manual',
  external_id text,
  status varchar(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','completed','declined','canceled')),
  contract_id uuid,
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_esign_org ON esign_request(org_id, created_at DESC);
"""


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS esign_request")
    op.execute("DROP TABLE IF EXISTS webauthn_challenge")
    op.execute("DROP TABLE IF EXISTS webauthn_credential")
