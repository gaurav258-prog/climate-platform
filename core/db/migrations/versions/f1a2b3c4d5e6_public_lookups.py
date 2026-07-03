"""public_lookups

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-07-03

Adds public_lookups: anonymous "check any address" lookups, kept SEPARATE from
customer_locations (which is scoped to an authenticated paying customer's registered
portfolio assets). Anonymous lookups are a different concern -- rate-limiting, lead-gen
signal, no customer_id -- so they get their own table rather than overloading the
customer-scoped one.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'public_lookups',
        sa.Column('lookup_id', sa.Text(), nullable=False),
        sa.Column('raw_address', sa.Text(), nullable=True),   # only set if geocoded from text
        sa.Column('latitude', sa.Numeric(8, 5), nullable=False),
        sa.Column('longitude', sa.Numeric(8, 5), nullable=False),
        sa.Column('h3_cell_r8', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='computing'),
        # 'cached_hit' | 'computing' | 'done' | 'failed'
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('lookup_id'),
    )
    op.create_index('idx_public_lookups_h3', 'public_lookups', ['h3_cell_r8'], postgresql_using='btree')
    op.create_index('idx_public_lookups_requested', 'public_lookups', ['requested_at'], postgresql_using='btree')


def downgrade() -> None:
    op.drop_table('public_lookups')
