"""ext_banking.epc_label + ifrs9_stage — per-loan regulatory attributes a bank provides for its book.

These are the per-exposure figures the physical-risk engine can't derive from location (collateral EPC label,
IFRS-9 credit stage). Together with residual_maturity_years they let a bank fill the Pillar 3 integrated columns
(Template 2 EPC, Template 5 staging/maturity) by uploading one supplementary per-loan file matched to their book,
instead of hand-typing. Nullable; a real book fills them, demo books leave them blank.

Revision ID: bank_loan_attributes_202608
Revises: bank_residual_maturity_202608
"""
from alembic import op

revision = "bank_loan_attributes_202608"
down_revision = "bank_residual_maturity_202608"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS epc_label VARCHAR(2)")
    op.execute("ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS ifrs9_stage VARCHAR(1)")


def downgrade() -> None:
    op.execute("ALTER TABLE ext_banking DROP COLUMN IF EXISTS epc_label")
    op.execute("ALTER TABLE ext_banking DROP COLUMN IF EXISTS ifrs9_stage")
