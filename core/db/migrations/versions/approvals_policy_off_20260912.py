"""Pending approvals lose their policy honestly — a 'withdrawn' status with a recorded cause.

When an org switches an action's 4-eyes rule off (or narrows it), pending requests for that action are no longer
governed by any rule. They are closed as `withdrawn` (cause `policy_no_longer_requires_approval`), never applied
and never left decidable. Widens the status CHECK on approval_requests (and on risk_decision, whose proposed
decision is withdrawn with its request) and adds `withdrawn_cause` so the flag is a first-class field.

Revision ID: approvals_policy_off_20260912
Revises: requests_sla_20260912, worker_heartbeat_20260912

Two other branches were cut from the same parent (relevance_model_version_20260912) by parallel
agents in this session (requests_sla_20260912, worker_heartbeat_20260912). Merging onto both here
keeps a single head instead of adding a third independent branch.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "approvals_policy_off_20260912"
down_revision: Union[str, Sequence[str], None] = ("requests_sla_20260912", "worker_heartbeat_20260912")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS withdrawn_cause TEXT")
    op.execute("ALTER TABLE approval_requests DROP CONSTRAINT IF EXISTS approval_requests_status_check")
    op.execute("ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_status_check "
               "CHECK (status IN ('pending','approved','rejected','returned','withdrawn'))")
    op.execute("ALTER TABLE risk_decision DROP CONSTRAINT IF EXISTS risk_decision_status_check")
    op.execute("ALTER TABLE risk_decision ADD CONSTRAINT risk_decision_status_check "
               "CHECK (status IN ('proposed','approved','rejected','withdrawn'))")


def downgrade() -> None:
    op.execute("UPDATE risk_decision SET status = 'rejected' WHERE status = 'withdrawn'")
    op.execute("ALTER TABLE risk_decision DROP CONSTRAINT IF EXISTS risk_decision_status_check")
    op.execute("ALTER TABLE risk_decision ADD CONSTRAINT risk_decision_status_check "
               "CHECK (status IN ('proposed','approved','rejected'))")
    op.execute("UPDATE approval_requests SET status = 'rejected' WHERE status = 'withdrawn'")
    op.execute("ALTER TABLE approval_requests DROP CONSTRAINT IF EXISTS approval_requests_status_check")
    op.execute("ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_status_check "
               "CHECK (status IN ('pending','approved','rejected','returned'))")
    op.execute("ALTER TABLE approval_requests DROP COLUMN IF EXISTS withdrawn_cause")
