"""Timestamp filing events with clock_timestamp(), not now().

now() returns the transaction start time, so two lifecycle events written in the same transaction tie and
the history sorts non-deterministically. clock_timestamp() is the real wall-clock at each INSERT, so every
event gets a distinct, monotonically increasing timestamp — the history always reads in the true order.

Revision ID: reg_filing_event_clock_20260803
Revises: reg_obligation_uniq_20260803
"""
from alembic import op

revision = "reg_filing_event_clock_20260803"
down_revision = "reg_obligation_uniq_20260803"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE regulatory_filing_event ALTER COLUMN created_at SET DEFAULT clock_timestamp()")


def downgrade() -> None:
    op.execute("ALTER TABLE regulatory_filing_event ALTER COLUMN created_at SET DEFAULT now()")
