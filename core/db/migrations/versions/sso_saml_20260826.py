"""SAML 2.0 IdP settings on the per-tenant SSO config.

Adds the SAML identity-provider fields (entity ID, SSO URL, signing certificate) alongside the existing OIDC
fields, so a tenant can connect an IdP that mandates SAML. The `protocol` column already permits 'saml'.
Idempotent for direct application to the demo DB.

Revision ID: sso_saml_20260826
Revises: sso_scim_20260826
"""
from alembic import op

revision = "sso_saml_20260826"
down_revision = "sso_scim_20260826"
branch_labels = None
depends_on = None

_DDL = """
ALTER TABLE tenant_sso_config ADD COLUMN IF NOT EXISTS saml_idp_entity_id text;
ALTER TABLE tenant_sso_config ADD COLUMN IF NOT EXISTS saml_idp_sso_url text;
ALTER TABLE tenant_sso_config ADD COLUMN IF NOT EXISTS saml_idp_x509_cert text;
"""


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    op.execute("ALTER TABLE tenant_sso_config DROP COLUMN IF EXISTS saml_idp_entity_id")
    op.execute("ALTER TABLE tenant_sso_config DROP COLUMN IF EXISTS saml_idp_sso_url")
    op.execute("ALTER TABLE tenant_sso_config DROP COLUMN IF EXISTS saml_idp_x509_cert")
