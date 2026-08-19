"""Agriculture commodity COGS-at-risk overrides (parity with the other 4 verticals)

Banking/insurance/real-estate/asset-management all let a pricing.approve user
correct a computed risk figure with a mandatory, audited reason -- agriculture
had no equivalent, even though its v0/uncalibrated COGS-at-risk model (see
services/intelligence/supply_cogs.py's HONESTY note) is exactly the kind of
figure a procurement analyst with on-the-ground supplier knowledge would
legitimately want to correct.

The override is keyed on (org_id, commodity_id), not a single entity_id like
the other verticals: sc_commodities is a small SHARED reference table (8 rows)
used by every org's book, and the COGS-at-risk figure itself is computed per
commodity (rolled up across that org's plots for the commodity), not per plot
-- see supply_cogs.compute()'s CommodityRisk. Overriding at plot level would
be the wrong granularity for what this number actually represents.

Revision ID: c3d4e5f6a7b8
Revises: b9c0d1e2f3a4
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE IF NOT EXISTS sc_commodity_overrides (
    org_id                       UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    commodity_id                 UUID NOT NULL REFERENCES sc_commodities(commodity_id) ON DELETE CASCADE,
    override_cogs_at_risk_p50_eur NUMERIC(14,2) NOT NULL,
    overridden_by                UUID REFERENCES users(user_id),
    overridden_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason                        TEXT,
    PRIMARY KEY (org_id, commodity_id)
);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS sc_commodity_overrides;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
