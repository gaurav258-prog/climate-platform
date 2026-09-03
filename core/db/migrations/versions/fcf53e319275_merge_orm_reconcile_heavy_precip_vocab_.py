"""merge orm_reconcile + heavy_precip_vocab heads

Revision ID: fcf53e319275
Revises: heavy_precip_vocab_20260831, orm_reconcile_20260831
Create Date: 2026-09-03 09:41:48.920429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fcf53e319275'
down_revision: Union[str, None] = ('heavy_precip_vocab_20260831', 'orm_reconcile_20260831')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
