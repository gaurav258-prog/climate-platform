"""P2 enterprise: refresh-token sessions, SCIM Groups, SAML SLO + assertion-replay protection.

Adds rotating refresh tokens (one row per active session, revocable + reuse-detectable), SCIM Group storage +
membership (mapped to roles), a SAML SLO endpoint URL, and a replay cache of consumed SAML assertion IDs.
Idempotent.

Revision ID: enterprise_p2_20260826
Revises: security_hardening_20260826
"""
from alembic import op

revision = "enterprise_p2_20260826"
down_revision = "security_hardening_20260826"
branch_labels = None
depends_on = None

_DDL = """
CREATE TABLE IF NOT EXISTS refresh_token (
  token_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  org_id uuid NOT NULL,
  token_hash text NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','rotated','revoked')),
  replaced_by uuid,
  user_agent text,
  ip text,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_refresh_token_hash ON refresh_token(token_hash);
CREATE INDEX IF NOT EXISTS ix_refresh_token_user ON refresh_token(user_id);

CREATE TABLE IF NOT EXISTS scim_group (
  group_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  external_id text,
  display_name text NOT NULL,
  mapped_role varchar(50),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_scim_group_org_name ON scim_group(org_id, lower(display_name));

CREATE TABLE IF NOT EXISTS scim_group_member (
  group_id uuid NOT NULL REFERENCES scim_group(group_id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS saml_assertion_seen (
  assertion_id text NOT NULL,
  org_id uuid NOT NULL,
  seen_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, assertion_id)
);

ALTER TABLE tenant_sso_config ADD COLUMN IF NOT EXISTS saml_idp_slo_url text;
"""


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS saml_assertion_seen")
    op.execute("DROP TABLE IF EXISTS scim_group_member")
    op.execute("DROP TABLE IF EXISTS scim_group")
    op.execute("DROP TABLE IF EXISTS refresh_token")
    op.execute("ALTER TABLE tenant_sso_config DROP COLUMN IF EXISTS saml_idp_slo_url")
