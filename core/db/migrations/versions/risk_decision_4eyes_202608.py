"""Forward-risk decisions become 4-eyes proposals — a decision is proposed by a maker and confirmed by a
second pair of eyes through the shared approval_requests machinery. Adds the approval link and the
proposed → approved / rejected status flow (replacing the interim open/done/void).

Revision ID: risk_decision_4eyes_202608
Revises: risk_decision_202608
"""
from alembic import op

revision = "risk_decision_4eyes_202608"
down_revision = "risk_decision_202608"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE risk_decision ADD COLUMN IF NOT EXISTS approval_request_id UUID REFERENCES approval_requests(request_id);
ALTER TABLE risk_decision ADD COLUMN IF NOT EXISTS decided_by_checker UUID REFERENCES users(user_id);
ALTER TABLE risk_decision ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;
-- drop the old CHECK FIRST, then migrate the interim statuses, then swap in the maker-checker flow
ALTER TABLE risk_decision DROP CONSTRAINT IF EXISTS risk_decision_status_check;
UPDATE risk_decision SET status = 'approved' WHERE status IN ('open', 'done');
UPDATE risk_decision SET status = 'rejected' WHERE status = 'void';
ALTER TABLE risk_decision ADD CONSTRAINT risk_decision_status_check CHECK (status IN ('proposed','approved','rejected'));
ALTER TABLE risk_decision ALTER COLUMN status SET DEFAULT 'proposed';
"""

DOWN = """
ALTER TABLE risk_decision DROP CONSTRAINT IF EXISTS risk_decision_status_check;
ALTER TABLE risk_decision ADD CONSTRAINT risk_decision_status_check CHECK (status IN ('open','done','void'));
ALTER TABLE risk_decision ALTER COLUMN status SET DEFAULT 'open';
ALTER TABLE risk_decision DROP COLUMN IF EXISTS confirmed_at;
ALTER TABLE risk_decision DROP COLUMN IF EXISTS decided_by_checker;
ALTER TABLE risk_decision DROP COLUMN IF EXISTS approval_request_id;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
