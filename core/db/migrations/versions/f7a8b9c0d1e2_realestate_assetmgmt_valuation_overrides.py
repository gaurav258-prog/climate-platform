"""realestate/assetmgmt valuation-override tables (Gap 4: parity with banking)

Banking has had POST/DELETE /asset/{id}/valuation-override since
b2c3d4e5f6a7_bank_asset_valuations.py -- a human with pricing.approve can
correct a recommended discount (bad geocoding, stale construction data) with
a mandatory reason, fully audited. Real estate and asset management shared
the same valuation_block()/discount-table engine but had no equivalent
correction path -- an asset manager who disagreed with a scored bucket had no
recourse at all, unlike a bank user. Same table shape, same audit discipline,
just two more asset types.

Revision ID: f7a8b9c0d1e2
Revises: d4e5f6a7b8c9
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE IF NOT EXISTS realestate_property_valuations (
    property_id         UUID PRIMARY KEY REFERENCES realestate_properties(property_id) ON DELETE CASCADE,
    override_discount_pct NUMERIC(5,2) NOT NULL,
    overridden_by        UUID REFERENCES users(user_id),
    overridden_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason                TEXT
);

CREATE TABLE IF NOT EXISTS assetmgmt_holding_valuations (
    holding_id          UUID PRIMARY KEY REFERENCES assetmgmt_holdings(holding_id) ON DELETE CASCADE,
    override_discount_pct NUMERIC(5,2) NOT NULL,
    overridden_by        UUID REFERENCES users(user_id),
    overridden_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason                TEXT
);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS realestate_property_valuations;
DROP TABLE IF EXISTS assetmgmt_holding_valuations;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
