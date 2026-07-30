"""Governance for location edits/deletes: an admin-editable approval matrix + permissions.

The 4-eyes engine (approval_requests) and audit log already exist. This adds:
  - approval_policy: the "approval matrix" — per-org, per-action rules deciding whether a
    change applies directly or must be approved by a second person. material_fields lets an
    UPDATE require approval only when a material field changes (coordinates, value, spend).
  - permissions supply.locations.write (maker) + admin.approval_policy.manage (matrix editor),
    granted to the existing roles.
  - a seed of platform-default policy rows (org_id NULL) for the four location actions.

Revision ID: governance_locations_20260729
Revises: sc_site_throughput_20260729
"""
from alembic import op

revision = "governance_locations_20260729"
down_revision = "sc_site_throughput_20260729"
branch_labels = None
depends_on = None

ACTIONS = [
    # (action_key, requires_approval, material_fields)
    ("supply.site.update", True, ["latitude", "longitude", "annual_value_eur", "annual_throughput_eur"]),
    ("supply.site.delete", True, []),
    ("supply.plot.update", True, ["latitude", "longitude", "annual_spend_eur"]),
    ("supply.plot.delete", True, []),
]

NEW_PERMS = [
    ("supply.locations.write", "Add, edit and delete operational sites and sourcing plots"),
    ("admin.approval_policy.manage", "View and edit the approval matrix (which actions need 4-eyes)"),
]


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS approval_policy (
            org_id            UUID REFERENCES organizations(org_id) ON DELETE CASCADE,
            action_key        TEXT NOT NULL,
            requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
            material_fields   JSONB NOT NULL DEFAULT '[]'::jsonb,
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by        UUID REFERENCES users(user_id)
        )
    """)
    # one policy row per (org, action); org_id NULL is the platform default. Partial unique
    # indexes because NULLs don't compare equal in a plain UNIQUE.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS approval_policy_org_action ON approval_policy (org_id, action_key) WHERE org_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS approval_policy_default_action ON approval_policy (action_key) WHERE org_id IS NULL")

    import json
    for key, req, fields in ACTIONS:
        op.execute(f"""
            INSERT INTO approval_policy (org_id, action_key, requires_approval, material_fields)
            VALUES (NULL, '{key}', {str(req).upper()}, '{json.dumps(fields)}'::jsonb)
            ON CONFLICT DO NOTHING
        """)

    for code, desc in NEW_PERMS:
        op.execute(f"INSERT INTO permissions (code, description) VALUES ('{code}', '{desc}') ON CONFLICT (code) DO NOTHING")

    # grant supply.locations.write to admin + analyst (makers); approval_policy.manage to admin only.
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id FROM roles r, permissions p
        WHERE r.name IN ('admin','analyst') AND p.code = 'supply.locations.write'
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id FROM roles r, permissions p
        WHERE r.name = 'admin' AND p.code = 'admin.approval_policy.manage'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT permission_id FROM permissions WHERE code IN ('supply.locations.write','admin.approval_policy.manage'))")
    op.execute("DELETE FROM permissions WHERE code IN ('supply.locations.write','admin.approval_policy.manage')")
    op.execute("DROP TABLE IF EXISTS approval_policy")
