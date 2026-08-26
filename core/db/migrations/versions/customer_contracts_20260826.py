"""customer_contract vault + contracts.view / contracts.manage RBAC permissions.

Signed customer agreements (MSA, DPA, SOW, order forms, NDA) stored against the tenant and gated by two new
permissions, so an org's members see them only per their role — admins & approvers by default, analysts not.
Files are stored as bytea (same pattern as regulatory_task_attachment). Access is audited in the router.

Revision ID: customer_contracts_20260826
Revises: bank_emission_intensity_202608
"""
from alembic import op

revision = "customer_contracts_20260826"
down_revision = "bank_emission_intensity_202608"
branch_labels = None
depends_on = None

_DDL = """
CREATE TABLE IF NOT EXISTS customer_contract (
    contract_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL,
    title           text NOT NULL,
    counterparty    text,
    contract_type   varchar(30) NOT NULL DEFAULT 'other',   -- msa/dpa/sow/order_form/nda/other
    status          varchar(20) NOT NULL DEFAULT 'active',   -- active/expired/terminated/draft
    signed_date     date,
    effective_date  date,
    expiry_date     date,
    filename        text NOT NULL,
    content_type    text,
    size_bytes      integer NOT NULL DEFAULT 0,
    data            bytea NOT NULL,
    uploaded_by     uuid,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_customer_contract_org ON customer_contract(org_id, created_at DESC);
"""

_PERMS = """
INSERT INTO permissions (permission_id, code, description) VALUES
    (gen_random_uuid(), 'contracts.view',   'View and download the organization''s signed customer contracts'),
    (gen_random_uuid(), 'contracts.manage', 'Upload, replace and remove customer contracts')
ON CONFLICT (code) DO NOTHING;
"""

# Grant to existing tenants' roles (new tenants get these via tenant_provisioning.DEFAULT_ROLE_PERMS):
# admin → view + manage; approver → view.
_GRANTS = """
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id FROM roles r, permissions p
WHERE r.name = 'admin' AND p.code IN ('contracts.view','contracts.manage')
ON CONFLICT DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id FROM roles r, permissions p
WHERE r.name = 'approver' AND p.code = 'contracts.view'
ON CONFLICT DO NOTHING;
"""


def upgrade() -> None:
    op.execute(_DDL)
    op.execute(_PERMS)
    op.execute(_GRANTS)


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT permission_id FROM permissions WHERE code LIKE 'contracts.%')")
    op.execute("DELETE FROM permissions WHERE code LIKE 'contracts.%'")
    op.execute("DROP TABLE IF EXISTS customer_contract")
