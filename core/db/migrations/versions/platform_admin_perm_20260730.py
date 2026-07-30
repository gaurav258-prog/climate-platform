"""platform.admin permission — the cross-tenant operator capability.

The whole app is org-scoped and deliberately hardened against cross-tenant reads. The
platform-operator console (Tellumen staff) is the ONE surface that reads across orgs, so it
needs a capability no customer role holds. This adds the permission only; the platform tenant,
its operator role, and the demo operator user are created by scripts/seed_platform_operator.py.

Revision ID: platform_admin_perm_20260730
Revises: governance_locations_20260729
"""
from alembic import op

revision = "platform_admin_perm_20260730"
down_revision = "governance_locations_20260729"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO permissions (code, description)
        VALUES ('platform.admin', 'Tellumen platform operator — read across all customer tenants')
        ON CONFLICT (code) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT permission_id FROM permissions WHERE code='platform.admin')")
    op.execute("DELETE FROM permissions WHERE code = 'platform.admin'")
