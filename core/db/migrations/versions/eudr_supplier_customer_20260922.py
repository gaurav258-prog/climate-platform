"""eudr_supplier_customer_identity

EUDR Art. 9(1)(e)/(f) — the due-diligence information system must collect the name, address and
contact details of both the immediate SUPPLIER and the immediate downstream CUSTOMER for each
relevant product. `sc_suppliers` only carried name/country/tier — no address, no email. There was
no concept of "who we sell to" anywhere in the schema (checked: no customer/buyer/downstream table
for the agri supply-chain vertical — `customer_contract` is an unrelated SaaS contract vault).

Adds address/contact_email (both nullable — real suppliers may not have submitted them yet, never
fabricated) to sc_suppliers, and a minimal sc_customers table mirroring sc_suppliers' shape for the
Art. 9(1)(f) downstream side.

Revision ID: eudr_supplier_customer_20260922
Revises: d9d0702196df
Create Date: 2026-09-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "eudr_supplier_customer_20260922"
down_revision: Union[str, None] = "d9d0702196df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPGRADE = """
ALTER TABLE sc_suppliers ADD COLUMN IF NOT EXISTS address        TEXT;
ALTER TABLE sc_suppliers ADD COLUMN IF NOT EXISTS contact_email  VARCHAR(320);

-- Art. 9(1)(f): "the name, postal address and email address of any business, operator or trader to
-- whom the relevant products have been supplied" — the operator's own downstream customers. Mirrors
-- sc_suppliers' shape (this is the same identity requirement, opposite direction of the chain).
CREATE TABLE IF NOT EXISTS sc_customers (
    customer_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    name           VARCHAR(160) NOT NULL,
    address        TEXT,
    contact_email  VARCHAR(320),
    country        VARCHAR(2),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_sc_customers_org ON sc_customers(org_id);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS sc_customers;
ALTER TABLE sc_suppliers DROP COLUMN IF EXISTS contact_email;
ALTER TABLE sc_suppliers DROP COLUMN IF EXISTS address;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
