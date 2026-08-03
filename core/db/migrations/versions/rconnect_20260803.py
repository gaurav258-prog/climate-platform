"""RConnect — submission case & communication tracker between the institution and its regulator.

Once a filing is submitted, the correspondence about it (acknowledgements, the regulator's queries, the
answers, closure) is a case that needs one home. This adds a case per submission with a five-stage tracker
(ready → submitted → query → answered → closed) and an append-only message thread. The message log is WORM
so the correspondence record is tamper-evident. The actual transmission channel to a regulator portal is
external and out of scope here — this is the institution-side case and comms record.

Revision ID: rconnect_20260803
Revises: regulatory_tasks_20260803
"""
from alembic import op

revision = "rconnect_20260803"
down_revision = "regulatory_tasks_20260803"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS reg_submission_case (
    case_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(org_id),
    filing_id   UUID REFERENCES regulatory_filing(filing_id),
    regulator   TEXT NOT NULL,
    reference   TEXT,
    stage       TEXT NOT NULL DEFAULT 'ready'
                 CHECK (stage IN ('ready','submitted','query','answered','closed')),
    created_by  UUID REFERENCES users(user_id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rcase_org ON reg_submission_case (org_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS reg_case_message (
    message_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id       UUID NOT NULL REFERENCES reg_submission_case(case_id),
    direction     TEXT NOT NULL CHECK (direction IN ('outbound','inbound')),
    author        TEXT NOT NULL,
    body          TEXT NOT NULL,
    attachment_ref TEXT,
    actor_user_id UUID REFERENCES users(user_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rcase_msg ON reg_case_message (case_id, created_at);
"""

GUARD = """
CREATE OR REPLACE FUNCTION prevent_case_message_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'reg_case_message is an append-only correspondence record; % is blocked', TG_OP;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_case_msg_worm ON reg_case_message;
CREATE TRIGGER trg_case_msg_worm BEFORE UPDATE OR DELETE ON reg_case_message
    FOR EACH ROW EXECUTE FUNCTION prevent_case_message_mutation();

CREATE OR REPLACE FUNCTION touch_case_updated() RETURNS trigger AS $$
BEGIN NEW.updated_at := now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_case_touch ON reg_submission_case;
CREATE TRIGGER trg_case_touch BEFORE UPDATE ON reg_submission_case
    FOR EACH ROW EXECUTE FUNCTION touch_case_updated();
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute(GUARD)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_case_touch ON reg_submission_case")
    op.execute("DROP TRIGGER IF EXISTS trg_case_msg_worm ON reg_case_message")
    op.execute("DROP FUNCTION IF EXISTS touch_case_updated()")
    op.execute("DROP FUNCTION IF EXISTS prevent_case_message_mutation()")
    op.execute("DROP TABLE IF EXISTS reg_case_message")
    op.execute("DROP TABLE IF EXISTS reg_submission_case")
