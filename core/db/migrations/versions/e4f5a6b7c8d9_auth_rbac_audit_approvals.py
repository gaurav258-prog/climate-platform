"""auth_rbac_audit_approvals

Real user auth + RBAC + audit + 4-eyes (maker-checker) + service portal.

The platform had org-level API keys but no notion of a real logged-in USER: the UI
picked "which customer you are" with a demo dropdown. This migration lays the DB
foundation for genuine login and role-scoped access:

- extends the existing `users` table with password / full_name / status (does NOT
  recreate it — users already exists from the bank-vertical migration),
- adds roles / permissions / role_permissions / user_roles (RBAC),
- adds org_entitlements (which offerings a tenant may see — replaces the hard-coded
  PERSONAS entitlements in the UI),
- adds a generic audit_log (distinct from the framework-scoped regulatory_audit_log),
- adds approval_requests for 4-eyes, with a DB-level CHECK (checker <> maker) that
  mirrors the existing ml/regulatory/packager.py maker-checker guard,
- adds service_requests for the customer support/service portal,
- seeds the global permissions catalog (roles + users are created by
  scripts/seed_auth_demo.py, per-org).

Revision ID: e4f5a6b7c8d9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DDL = """
-- (A) Extend existing users table (do NOT recreate) ----------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name       VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_password TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS status          VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at   TIMESTAMPTZ;
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_status_chk CHECK (status IN ('active','disabled'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- (B) Roles (per-org; org_id NULL = global template) ---------------------
CREATE TABLE IF NOT EXISTS roles (
    role_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID REFERENCES organizations(org_id) ON DELETE CASCADE,
    name        VARCHAR(50)  NOT NULL,
    description TEXT,
    is_system   BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, name)
);

-- (C) Permissions catalog (global) ---------------------------------------
CREATE TABLE IF NOT EXISTS permissions (
    permission_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code          VARCHAR(80) NOT NULL UNIQUE,
    description   TEXT
);

-- (D) role <-> permission (editable matrix) ------------------------------
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       UUID NOT NULL REFERENCES roles(role_id)             ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(permission_id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- (E) user <-> role ------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_roles (
    user_id    UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role_id    UUID NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by UUID REFERENCES users(user_id),
    PRIMARY KEY (user_id, role_id)
);

-- (F) Tenant entitlements (replaces hard-coded PERSONAS) -----------------
CREATE TABLE IF NOT EXISTS org_entitlements (
    org_id      UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    offering_id VARCHAR(50) NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (org_id, offering_id)
);

-- (G) Access/RBAC audit log ---------------------------------------------
-- Named access_audit_log to avoid colliding with the pre-existing, trigger-fed
-- `audit_log` (row-change audit) and the framework-scoped `regulatory_audit_log`.
CREATE TABLE IF NOT EXISTS access_audit_log (
    audit_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID REFERENCES organizations(org_id) ON DELETE SET NULL,
    actor_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    action        VARCHAR(80) NOT NULL,
    target_type   VARCHAR(80),
    target_id     VARCHAR(120),
    detail        JSONB,
    ip            VARCHAR(64),
    user_agent    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_access_audit_org_time ON access_audit_log (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_access_audit_actor    ON access_audit_log (actor_user_id);
CREATE INDEX IF NOT EXISTS ix_access_audit_action   ON access_audit_log (action);

-- (H) 4-eyes approval requests ------------------------------------------
CREATE TABLE IF NOT EXISTS approval_requests (
    request_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    request_type    VARCHAR(60) NOT NULL,
    title           TEXT,
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','rejected')),
    maker_user_id   UUID NOT NULL REFERENCES users(user_id),
    checker_user_id UUID REFERENCES users(user_id),
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at      TIMESTAMPTZ,
    CHECK (checker_user_id IS NULL OR checker_user_id <> maker_user_id)
);
CREATE INDEX IF NOT EXISTS ix_approvals_org_status ON approval_requests (org_id, status);

-- (I) Service portal requests -------------------------------------------
CREATE TABLE IF NOT EXISTS service_requests (
    request_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    requester_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    category          VARCHAR(40) NOT NULL,
    subject           VARCHAR(200) NOT NULL,
    body              TEXT,
    priority          VARCHAR(20) NOT NULL DEFAULT 'normal'
                      CHECK (priority IN ('low','normal','high','urgent')),
    status            VARCHAR(20) NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open','in_progress','resolved')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_service_requests_org_status ON service_requests (org_id, status);
"""

# Global permissions catalog. Roles + role_permissions + users are seeded per-org
# by scripts/seed_auth_demo.py so this migration stays data-light and org-agnostic.
PERMISSIONS = [
    ("modules.view",        "View and use the analytical modules"),
    ("reports.view",        "View disclosure reports"),
    ("reports.publish",     "Publish/finalise a disclosure report"),
    ("pricing.view",        "View pricing outputs"),
    ("pricing.approve",     "Approve a pricing change"),
    ("admin.users.manage",  "Create, edit and disable users"),
    ("admin.roles.manage",  "Edit roles and the permission matrix"),
    ("admin.audit.view",    "View the audit trail"),
    ("approvals.create",    "Submit a maker request for approval"),
    ("approvals.view",      "View the approvals queue"),
    ("approvals.decide",    "Approve or reject a request (checker)"),
    ("portal.use",          "Raise and view service-portal requests"),
]


def upgrade() -> None:
    op.execute(DDL)
    for code, desc in PERMISSIONS:
        op.execute(
            "INSERT INTO permissions (code, description) VALUES "
            f"('{code}', '{desc}') ON CONFLICT (code) DO NOTHING"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS service_requests")
    op.execute("DROP TABLE IF EXISTS approval_requests")
    op.execute("DROP TABLE IF EXISTS access_audit_log")
    op.execute("DROP TABLE IF EXISTS org_entitlements")
    op.execute("DROP TABLE IF EXISTS user_roles")
    op.execute("DROP TABLE IF EXISTS role_permissions")
    op.execute("DROP TABLE IF EXISTS permissions")
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_status_chk")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_login_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS hashed_password")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS full_name")
