"""Regulatory work tasks — the Kanban backbone for the reporting workflow.

Filings have a lifecycle, but the PEOPLE doing the work need somewhere to see and move their tasks:
"import the market-risk file", "investigate a failed validation", "generate the XBRL", "run the 4-eyes
approval". This adds a persistent, assignable task with a Kanban status, a due date, an optional link to a
filing, a source (so a validation exception or an obligation can spin one up), and simple dependencies.

Statuses map to Kanban columns: icebox → todo → blocked → doing → review → done (+ cancelled).
Append-only activity is captured in regulatory_task_event so who-moved-what-when is auditable.

Revision ID: regulatory_tasks_20260803
Revises: reg_filing_event_clock_20260803
"""
from alembic import op

revision = "regulatory_tasks_20260803"
down_revision = "reg_filing_event_clock_20260803"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS regulatory_task (
    task_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES organizations(org_id),
    title          TEXT NOT NULL,
    description    TEXT,
    status         TEXT NOT NULL DEFAULT 'todo'
                    CHECK (status IN ('icebox','todo','blocked','doing','review','done','cancelled')),
    criticality    TEXT NOT NULL DEFAULT 'normal'
                    CHECK (criticality IN ('low','normal','high','critical')),
    assignee_user_id UUID REFERENCES users(user_id),
    filing_id      UUID REFERENCES regulatory_filing(filing_id),
    source         TEXT NOT NULL DEFAULT 'manual'
                    CHECK (source IN ('manual','validation','exception','obligation','regulatory_change')),
    source_ref     TEXT,                       -- e.g. a validation rule key, so we don't duplicate a task
    due_date       DATE,
    depends_on     UUID[] NOT NULL DEFAULT '{}',
    position       DOUBLE PRECISION NOT NULL DEFAULT 0,   -- ordering within a column
    created_by     UUID REFERENCES users(user_id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_reg_task_org_status ON regulatory_task (org_id, status);
CREATE INDEX IF NOT EXISTS ix_reg_task_assignee   ON regulatory_task (assignee_user_id);
CREATE INDEX IF NOT EXISTS ix_reg_task_filing     ON regulatory_task (filing_id);
-- one live task per (org, source, source_ref) so a re-run validation doesn't pile up duplicates
CREATE UNIQUE INDEX IF NOT EXISTS ux_reg_task_source
    ON regulatory_task (org_id, source, source_ref)
    WHERE source_ref IS NOT NULL AND status <> 'cancelled' AND status <> 'done';

CREATE TABLE IF NOT EXISTS regulatory_task_event (
    event_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id      UUID NOT NULL REFERENCES regulatory_task(task_id),
    kind         TEXT NOT NULL,                -- created | moved | assigned | edited | commented
    from_val     TEXT,
    to_val       TEXT,
    note         TEXT,
    actor_user_id UUID REFERENCES users(user_id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_reg_task_event ON regulatory_task_event (task_id, created_at);
"""

GUARD = """
CREATE OR REPLACE FUNCTION prevent_task_event_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'regulatory_task_event is append-only; % is blocked', TG_OP;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_task_event_worm ON regulatory_task_event;
CREATE TRIGGER trg_task_event_worm
    BEFORE UPDATE OR DELETE ON regulatory_task_event
    FOR EACH ROW EXECUTE FUNCTION prevent_task_event_mutation();

CREATE OR REPLACE FUNCTION touch_task_updated() RETURNS trigger AS $$
BEGIN NEW.updated_at := now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_task_touch ON regulatory_task;
CREATE TRIGGER trg_task_touch BEFORE UPDATE ON regulatory_task
    FOR EACH ROW EXECUTE FUNCTION touch_task_updated();
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute(GUARD)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_task_touch ON regulatory_task")
    op.execute("DROP TRIGGER IF EXISTS trg_task_event_worm ON regulatory_task_event")
    op.execute("DROP FUNCTION IF EXISTS touch_task_updated()")
    op.execute("DROP FUNCTION IF EXISTS prevent_task_event_mutation()")
    op.execute("DROP TABLE IF EXISTS regulatory_task_event")
    op.execute("DROP TABLE IF EXISTS regulatory_task")
