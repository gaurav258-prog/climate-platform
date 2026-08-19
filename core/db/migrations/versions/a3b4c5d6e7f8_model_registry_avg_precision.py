"""model_registry_avg_precision

Record the honest skill metric. ROC-AUC overstates rare-event models badly: at a
~1-in-3,400 base rate a model can score AUC 0.99 while its Average Precision is
~0.04 and it cannot operationally pick out the cells that actually flood/burn.
Adds validation_avg_precision (the honest metric) and validation_note (the caveat
— e.g. single proxy-labeled event, forecasting untested) so nothing downstream
quotes AUC as if it were skill.

Revision ID: a3b4c5d6e7f8
Revises: f2a5b6c7d8e9
Create Date: 2026-06-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("model_registry", sa.Column("validation_avg_precision", sa.Numeric(6, 5)))
    op.add_column("model_registry", sa.Column("validation_note", sa.Text()))


def downgrade() -> None:
    op.drop_column("model_registry", "validation_note")
    op.drop_column("model_registry", "validation_avg_precision")
