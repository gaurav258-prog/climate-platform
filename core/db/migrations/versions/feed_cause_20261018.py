"""A failed feed refresh records its cause (E215).

The refresh log said why a refresh failed only in its note's words, so a provider's outage (a 502 from its gateway) and
a fault in our adapter could be told apart only by matching text. The cause is now a field:

  feed_refresh_log  + cause: 'source_unreachable' (the provider could not be reached or answered 502/503/504, or the
                      adapter said so after its retries) | 'adapter_fault' (anything else); set on a failed refresh only

Rows recorded before this revision keep no cause (their notes still say what happened). The downgrade drops the field;
each failure's note keeps its words ('source unreachable (…)' for an outage), so nothing that was said is lost.

Revision ID: feed_cause_20261018
Revises: loss_msg_20261017
"""
from typing import Sequence, Union

from alembic import op

revision: str = "feed_cause_20261018"
down_revision: Union[str, None] = "loss_msg_20261017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE feed_refresh_log
            ADD COLUMN cause varchar(20),
            ADD CONSTRAINT feed_refresh_log_cause_kind CHECK (cause IN ('source_unreachable', 'adapter_fault')),
            ADD CONSTRAINT feed_refresh_log_cause_on_failure CHECK (cause IS NULL OR status = 'failed');
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE feed_refresh_log DROP CONSTRAINT feed_refresh_log_cause_on_failure,
            DROP CONSTRAINT feed_refresh_log_cause_kind, DROP COLUMN cause;
    """)
