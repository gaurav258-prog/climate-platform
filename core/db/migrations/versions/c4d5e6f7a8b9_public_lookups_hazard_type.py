"""public_lookups_hazard_type

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-04

Adds hazard_type to public_lookups. Without it, api/routers/lookup.py's
_compute_overall() could only COUNT 'computing' rows for a cell, not tell which
distinct hazards they belonged to — a real accuracy bug found live: since
lookup_score() doesn't check for an already-in-flight job before starting a new
one, repeated calls for the same uncached address create duplicate rows for the
same hazard, inflating the raw pending count and silently under-counting
hazards_insufficient (a subtraction-then-clamp formula, not a direct count).
Nullable: the unconditional "log the whole request" row lookup_score() also
writes doesn't correspond to a single hazard.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('public_lookups', sa.Column('hazard_type', sa.String(20), nullable=True))
    op.create_index('idx_public_lookups_cell_hazard', 'public_lookups',
                     ['h3_cell_r8', 'hazard_type', 'status'], postgresql_using='btree')


def downgrade() -> None:
    op.drop_index('idx_public_lookups_cell_hazard', table_name='public_lookups')
    op.drop_column('public_lookups', 'hazard_type')
