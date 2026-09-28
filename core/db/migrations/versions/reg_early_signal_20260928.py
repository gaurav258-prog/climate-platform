"""CRCS early warning: items from regulators' own feeds and the news that may announce a change — unconfirmed.

reg_early_signal  one row per item (unique by URL): source, title, summary, published, the topics / frameworks it
                  concerns, and its status — unconfirmed until the official register records a change for one of
                  those frameworks after it was published (then 'register_confirmed', linked), or 'dismissed'.

Revision ID: reg_early_signal_20260928
Revises: retention_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "reg_early_signal_20260928"
down_revision: Union[str, None] = "retention_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS reg_early_signal (
            signal_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_key      TEXT NOT NULL,
            jurisdiction    TEXT NOT NULL,
            url             TEXT NOT NULL UNIQUE,
            title           TEXT NOT NULL,
            summary         TEXT,
            published_at    TIMESTAMPTZ,
            topics          TEXT[] NOT NULL DEFAULT '{}',
            frameworks      TEXT[] NOT NULL DEFAULT '{}',
            status          TEXT NOT NULL DEFAULT 'unconfirmed'
                            CONSTRAINT ck_reg_early_signal CHECK (status IN ('unconfirmed', 'register_confirmed', 'dismissed')),
            confirmed_by    UUID,
            first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reg_early_signal_pub ON reg_early_signal (published_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reg_early_signal")
