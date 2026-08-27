"""Role-shaped navigation permissions — oversight.view, ops.oversee, decisions.view.

The sidebar was condensed into hubs and made strictly role-shaped: a role sees only the surfaces it may use.
Three capabilities gained their own permission so a role can hold them independently of the blanket
modules.view — the Supervisory view, the operate/monitor surfaces (Control Tower + compliance Calendar), and
the Decisions surface. Catalog only; role grants are set by DEFAULT_ROLE_PERMS (tenant_provisioning) for new
tenants and reconciled for existing tenants by scripts/reconcile_role_perms.py.

Revision ID: nav_role_perms_20260827
Revises: reg_alert_20260827
"""
from alembic import op

revision = "nav_role_perms_20260827"
down_revision = "reg_alert_20260827"
branch_labels = None
depends_on = None

NEW = [
    ("oversight.view", "See the Supervisory view — how a regulator will read your data"),
    ("ops.oversee", "Operate the control surfaces — Control Tower exceptions and the compliance calendar"),
    ("decisions.view", "See and work the Decisions surface (reprice / engage / act)"),
]


def upgrade() -> None:
    for code, desc in NEW:
        op.execute(
            "INSERT INTO permissions (code, description) VALUES "
            f"('{code}', '{desc}') ON CONFLICT (code) DO NOTHING"
        )


def downgrade() -> None:
    for code, _ in NEW:
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN "
                   f"(SELECT permission_id FROM permissions WHERE code='{code}')")
        op.execute(f"DELETE FROM permissions WHERE code = '{code}'")
