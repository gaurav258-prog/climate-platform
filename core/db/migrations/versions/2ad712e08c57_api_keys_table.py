"""api_keys_table

Revision ID: 2ad712e08c57
Revises: 80739a9ddc61
Create Date: 2026-06-24 22:49:14.105871

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '2ad712e08c57'
down_revision: Union[str, None] = '80739a9ddc61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("key_id",      sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("key_hash",    sa.Text,               nullable=False, unique=True),
        sa.Column("key_prefix",  sa.String(12),         nullable=False),
        sa.Column("name",        sa.Text,               nullable=False),
        sa.Column("is_active",   sa.Boolean,            nullable=False, server_default="true"),
        sa.Column("created_at",  sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at",   sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_customer_id", "api_keys", ["customer_id"])
    op.create_index("ix_api_keys_key_hash",    "api_keys", ["key_hash"])


def downgrade() -> None:
    op.drop_table("api_keys")
