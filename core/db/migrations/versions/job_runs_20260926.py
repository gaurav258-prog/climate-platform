"""Scheduled-job run record: the last run of every Celery task, so a stopped scheduler or a failing job shows as
OVERDUE / FAILED instead of silently never happening.

  * job_runs — one row per task name: last start, last finish, last status (ok | failed) and error, run and failure
    counts. Written by the worker's task signals (services/tasks/schedule_health.py).
The scheduler (celery beat) itself beats into worker_heartbeat with queue 'beat', kept apart from worker liveness.

Revision ID: job_runs_20260926
Revises: intake_dropfolder_20260925
"""
from typing import Sequence, Union

from alembic import op

revision: str = "job_runs_20260926"
down_revision: Union[str, None] = "intake_dropfolder_20260925"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS job_runs (
            task_name         TEXT PRIMARY KEY,
            last_started_at   TIMESTAMPTZ,
            last_finished_at  TIMESTAMPTZ,
            last_status       TEXT,
            last_error        TEXT,
            last_duration_ms  INTEGER,
            n_runs            INTEGER NOT NULL DEFAULT 0,
            n_failures        INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT ck_job_runs_status CHECK (last_status IS NULL OR last_status IN ('running', 'ok', 'failed'))
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_runs")
