"""merge bank govt-level and insurer motor-SI branches

Revision ID: d9d0702196df
Revises: bank_govt_level_20260922, ext_ins_motor_si_20260922
Create Date: 2026-09-22 14:06:49.324726

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9d0702196df'
down_revision: Union[str, None] = ('bank_govt_level_20260922', 'ext_ins_motor_si_20260922')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
