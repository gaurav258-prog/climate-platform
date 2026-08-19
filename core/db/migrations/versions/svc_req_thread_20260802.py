"""Service-request conversation thread + lifecycle timestamps.

The service portal (service_requests) let a customer raise a request and track a status, but there was no
way to actually CONVERSE — the customer couldn't add detail after the fact, and Tellumen support had no
channel to reply. This makes the "raise a request WITH US" loop real:

  * service_request_messages — a threaded log, customer ⇄ support, each entry sided and attributed.
  * first_response_at / resolved_at — the lifecycle timestamps that let us show a real SLA, not a guess.
  * assigned_to_user_id — routes a request to a named Tellumen operator (nullable; unassigned = anyone).

Additive and idempotent. Nothing here is customer-tunable calibration — it's the support workflow itself.

Revision ID: svc_req_thread_202608
Revises: approval_assignee_202608
"""
from alembic import op

revision = "svc_req_thread_202608"
down_revision = "approval_assignee_202608"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS service_request_messages (
    message_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id     UUID NOT NULL REFERENCES service_requests(request_id) ON DELETE CASCADE,
    author_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    author_side    VARCHAR(12) NOT NULL CHECK (author_side IN ('customer','support')),
    body           TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_srm_request_time ON service_request_messages (request_id, created_at);

ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS assigned_to_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL;
ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS first_response_at   TIMESTAMPTZ;
ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS resolved_at         TIMESTAMPTZ;
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS service_request_messages")
    op.execute("ALTER TABLE service_requests DROP COLUMN IF EXISTS assigned_to_user_id")
    op.execute("ALTER TABLE service_requests DROP COLUMN IF EXISTS first_response_at")
    op.execute("ALTER TABLE service_requests DROP COLUMN IF EXISTS resolved_at")
