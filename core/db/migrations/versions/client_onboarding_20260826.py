"""Client-onboarding lifecycle: pre-tenant intake, roster, documents, activation tokens, MFA, data residency.

Adds the commercial-onboarding tables that sit *before* a tenant exists (client_intake + roster + documents),
the per-user activation/set-password token table, MFA columns + the 'invited' user status for activation-pending
accounts, and a data-residency region on organizations. Everything is idempotent (IF NOT EXISTS / ON CONFLICT)
so it can be applied directly to a running demo DB as well as through Alembic.

Revision ID: client_onboarding_20260826
Revises: customer_contracts_20260826
"""
from alembic import op

revision = "client_onboarding_20260826"
down_revision = "customer_contracts_20260826"
branch_labels = None
depends_on = None

_DDL = """
-- data residency on organizations (EU default for the EU beachhead)
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS region varchar(20) NOT NULL DEFAULT 'EU';

-- activation-pending users sit in 'invited' until they set a password
-- (the base schema ships two differently-named status checks; drop both, add one that allows 'invited')
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_status_chk;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_status_check;
ALTER TABLE users ADD CONSTRAINT users_status_check CHECK (status IN ('active','disabled','invited'));

-- MFA (TOTP) enrolment on the user
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enrolled_at timestamptz;

-- pre-tenant client application
CREATE TABLE IF NOT EXISTS client_intake (
  intake_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_name varchar(255) NOT NULL,
  org_type varchar(50) NOT NULL,
  country varchar(2),
  region varchar(20) NOT NULL DEFAULT 'EU',
  legal_name varchar(300),
  lei varchar(20),
  filing_contact_email varchar(200),
  aum_eur numeric(18,2),
  employees int,
  contact_name varchar(255),
  contact_email varchar(255) NOT NULL,
  modules jsonb NOT NULL DEFAULT '[]'::jsonb,
  status varchar(20) NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','invited','submitted','in_review','provisioned','rejected')),
  token_hash text,
  token_expires_at timestamptz,
  provisioned_org_id uuid REFERENCES organizations(org_id) ON DELETE SET NULL,
  notes text,
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  submitted_at timestamptz,
  provisioned_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_client_intake_status ON client_intake(status);
CREATE INDEX IF NOT EXISTS ix_client_intake_token ON client_intake(token_hash);

-- the user roster to create on provisioning
CREATE TABLE IF NOT EXISTS client_intake_user (
  roster_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  intake_id uuid NOT NULL REFERENCES client_intake(intake_id) ON DELETE CASCADE,
  email varchar(255) NOT NULL,
  full_name varchar(255),
  role varchar(50) NOT NULL DEFAULT 'viewer',
  created_user_id uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_client_intake_user_intake ON client_intake_user(intake_id);

-- documents attached at intake (bytea); optionally filed to the contracts vault on provisioning
CREATE TABLE IF NOT EXISTS client_intake_document (
  document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  intake_id uuid NOT NULL REFERENCES client_intake(intake_id) ON DELETE CASCADE,
  kind varchar(30) NOT NULL DEFAULT 'other',
  title varchar(300),
  filename varchar(300),
  content_type varchar(120),
  data bytea NOT NULL,
  size_bytes int NOT NULL DEFAULT 0,
  to_vault boolean NOT NULL DEFAULT false,
  contract_type varchar(30),
  uploaded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_client_intake_document_intake ON client_intake_document(intake_id);

-- per-user activation / set-password tokens (hashed)
CREATE TABLE IF NOT EXISTS user_activation (
  activation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  org_id uuid NOT NULL,
  token_hash text NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','used','expired')),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  used_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_user_activation_token ON user_activation(token_hash);
CREATE INDEX IF NOT EXISTS ix_user_activation_user ON user_activation(user_id);
"""

_PERMS = """
INSERT INTO permissions (code, description) VALUES
  ('onboarding.manage','Create, review and provision client intakes')
ON CONFLICT (code) DO NOTHING;
"""

_GRANTS = """
INSERT INTO role_permissions (role_id, permission_id)
  SELECT r.role_id, p.permission_id
  FROM roles r CROSS JOIN permissions p
  WHERE p.code = 'onboarding.manage' AND r.name = 'platform-operator'
ON CONFLICT DO NOTHING;
"""


def upgrade() -> None:
    op.execute(_DDL)
    op.execute(_PERMS)
    op.execute(_GRANTS)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_activation")
    op.execute("DROP TABLE IF EXISTS client_intake_document")
    op.execute("DROP TABLE IF EXISTS client_intake_user")
    op.execute("DROP TABLE IF EXISTS client_intake")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_secret")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_enrolled_at")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS region")
