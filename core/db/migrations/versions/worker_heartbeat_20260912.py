"""worker_heartbeat — every job executor (the Celery worker, or the fallback child process while it runs a job)
writes its own row every HEARTBEAT_INTERVAL_S; a queued job with no fresh row is honestly "worker unavailable"
instead of "queued" forever (regulator module backlog item 4).

Revision ID: worker_heartbeat_20260912
Revises: relevance_model_version_20260912
"""
from typing import Sequence, Union

from alembic import op

revision: str = "worker_heartbeat_20260912"
down_revision: Union[str, None] = "relevance_model_version_20260912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS worker_heartbeat (
            worker     TEXT PRIMARY KEY,               -- celery node name (celery@host) or child:<pid>:<job>
            queue      TEXT NOT NULL,                  -- queues consumed ('celery') or 'process' for the fallback child
            hostname   TEXT NOT NULL,
            last_seen  TIMESTAMPTZ NOT NULL,
            version    TEXT NOT NULL,                  -- package version the executor runs
            started_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_worker_heartbeat_last_seen ON worker_heartbeat (last_seen DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS worker_heartbeat")
