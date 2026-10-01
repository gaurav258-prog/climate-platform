"""ext_realestate gains sum_insured_eur — a property's insured value, the base of what its insurance costs.

The operating-income drag priced a property's insurance on its market value, as though market value were the sum
insured (E69). The insured value is the owner's own figure (buildings reinstatement value), not its market value; it
is now a field of the property schedule. Without it the insurance cost is a named gap, never assumed.

Revision ID: reit_sum_insured_20260930
Revises: esrs_kri_bands_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "reit_sum_insured_20260930"
down_revision: Union[str, None] = "esrs_kri_bands_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE ext_realestate ADD COLUMN sum_insured_eur NUMERIC CHECK (sum_insured_eur > 0)")


def downgrade() -> None:
    op.execute("ALTER TABLE ext_realestate DROP COLUMN sum_insured_eur")
