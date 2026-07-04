"""bank_asset_valuations

Real lending-decision output for banking: bank_assets/v_bank_asset_physical_risk
stopped at "here's a risk score" -- no LTV/valuation-discount concept existed
anywhere in the schema. This adds the "current override state" for a
system-recommended-but-overridable valuation haircut per asset (see
ml/scoring/valuation_discount.py for the recommendation schedule). Full
change history lives in the EXISTING access_audit_log table via the EXISTING
write_audit() helper (api/services/rbac.py) -- this table only needs to hold
the CURRENT effective override, not a log of every past one.

Revision ID: b2c3d4e5f6a7
Revises: 9f8e7d6c5b4a
Create Date: 2026-07-04

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "9f8e7d6c5b4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE IF NOT EXISTS bank_asset_valuations (
    asset_id             UUID PRIMARY KEY REFERENCES bank_assets(asset_id) ON DELETE CASCADE,
    override_discount_pct NUMERIC(5,2),
    overridden_by        UUID REFERENCES users(user_id) ON DELETE SET NULL,
    overridden_at        TIMESTAMPTZ,
    reason               TEXT
);
"""

DOWNGRADE = "DROP TABLE IF EXISTS bank_asset_valuations;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
