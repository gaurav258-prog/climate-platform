"""Enterprise SSO (OIDC) + SCIM 2.0 auto-provisioning — per-tenant identity configuration.

The enterprise identity path benchmarked in the onboarding lifecycle: a tenant connects its own IdP (Okta /
Entra ID) so users sign in via OIDC and are auto-provisioned/deprovisioned via SCIM 2.0, instead of the
per-user activation-link path. This adds the per-tenant config plus the identity-mapping columns on users.
Idempotent so it can be applied directly to a running demo DB.

Revision ID: sso_scim_20260826
Revises: client_onboarding_20260826
"""
from alembic import op

revision = "sso_scim_20260826"
down_revision = "client_onboarding_20260826"
branch_labels = None
depends_on = None

_DDL = """
-- per-tenant SSO / SCIM configuration
CREATE TABLE IF NOT EXISTS tenant_sso_config (
  org_id uuid PRIMARY KEY REFERENCES organizations(org_id) ON DELETE CASCADE,
  protocol varchar(10) NOT NULL DEFAULT 'oidc' CHECK (protocol IN ('oidc','saml')),
  enabled boolean NOT NULL DEFAULT false,
  oidc_issuer text,
  oidc_client_id text,
  oidc_client_secret text,
  allowed_email_domain varchar(255),
  jit_provisioning boolean NOT NULL DEFAULT true,
  default_role varchar(50) NOT NULL DEFAULT 'viewer',
  scim_enabled boolean NOT NULL DEFAULT false,
  scim_token_hash text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_tenant_sso_scim_token ON tenant_sso_config(scim_token_hash);

-- SSO/SCIM identity mapping on the user (SSO users carry no local password)
ALTER TABLE users ADD COLUMN IF NOT EXISTS external_id text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider varchar(20) NOT NULL DEFAULT 'local';
CREATE INDEX IF NOT EXISTS ix_users_external_id ON users(org_id, external_id);
"""


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_sso_config")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS external_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auth_provider")
