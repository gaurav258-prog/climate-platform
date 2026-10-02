"""Each job executor's heartbeat names the jobs it can run (E110): a worker started on older code beat as 'alive' and
silently refused a job added since ('Received unregistered task'), so the caller was told the job was queued.

worker_heartbeat.jobs — the job names the executor registered at start (NULL: an executor that does not say, treated as
knowing none). services.tasks.jobs.submit sends a job to the worker only when a live one names it.

Revision ID: worker_jobs_20261001
Revises: signoff_sequence_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "worker_jobs_20261001"
down_revision: Union[str, None] = "signoff_sequence_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE worker_heartbeat ADD COLUMN jobs TEXT[]")


def downgrade() -> None:
    op.execute("ALTER TABLE worker_heartbeat DROP COLUMN jobs")
