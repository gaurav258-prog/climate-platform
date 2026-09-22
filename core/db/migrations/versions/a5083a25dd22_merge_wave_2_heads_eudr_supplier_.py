"""merge wave 2 heads: eudr supplier/customer, ifrs s2 incurred, sfdr dual kpi

Revision ID: a5083a25dd22
Revises: eudr_supplier_customer_20260922, ifrs_s2_incurred_20260922, sfdr_am_dualkpi_precon_20260922
Create Date: 2026-09-22 14:40:14.319709

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a5083a25dd22'
down_revision: Union[str, None] = ('eudr_supplier_customer_20260922', 'ifrs_s2_incurred_20260922', 'sfdr_am_dualkpi_precon_20260922')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
