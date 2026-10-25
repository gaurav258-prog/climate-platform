"""A loss figure says which value it is a share of when that value was not stated as such (the product owner's decisions of
2026-10-25: the building's part of a stated property value from official statistics, for an organisation that adopts it).

  loss_results  + value_basis: {code, share, source, area, period, lower_bound, stated_value_eur} where the exposed
                  value is the stated value times an official building share (services/reference/building_share.py);
                  NULL where the value is the one the book states

The downgrade drops the column.

Revision ID: loss_value_basis_20261025
Revises: coastal_protection_20261023
"""
from typing import Sequence, Union

from alembic import op

revision: str = "loss_value_basis_20261025"
down_revision: Union[str, None] = "coastal_protection_20261023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE loss_results ADD COLUMN value_basis JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE loss_results DROP COLUMN value_basis")
