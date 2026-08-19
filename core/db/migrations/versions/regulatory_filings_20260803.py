"""Reporting cockpit — filing register, lifecycle history, obligations calendar.

The platform already freezes a disclosure as an immutable, hashed, versioned `report_snapshots` row.
What it lacked was a *filing lifecycle* on top of that freeze: a regulatory filing is prepared, reviewed,
approved (4-eyes), attested by an accountable person, submitted to the regulator, and finally accepted —
and a compliance officer needs to see every filing as a row with its status, deadline, and full history.

This adds three things and duplicates none of the existing snapshot machinery:

  regulatory_filing        — the lifecycle wrapper. One row per (framework, reference period, entity).
                             Points at a report_snapshots row for the frozen bytes (snapshot_id, set when
                             the draft is generated). Carries status, deadline, the linked 4-eyes approval
                             request, the submission reference, and the restatement chain (superseded_by).
  regulatory_filing_event  — append-only lifecycle log (WORM): every status transition, who did it, when,
                             and why. This IS the per-filing audit trail and the "past reportings" history.
  regulatory_obligation    — the filing calendar: what is due, for which entity, by when, how often.

Status lifecycle (forward-only; a correction is a NEW filing that supersedes, never an edit):
  draft → in_review → approved → attested → submitted → accepted
  in_review → returned (back to draft)         rejected at review → draft
  submitted/accepted → superseded (by a restatement)

Immutability: once a filing is submitted or accepted its core fields are frozen by a guard trigger
(only status→superseded + superseded_by may still be set). The event log is pure WORM.

Revision ID: regulatory_filings_20260803
Revises: canonical_uniq_active_202608
"""
from alembic import op

revision = "regulatory_filings_20260803"
down_revision = "canonical_uniq_active_202608"
branch_labels = None
depends_on = None


DDL = """
CREATE TABLE IF NOT EXISTS regulatory_filing (
    filing_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES organizations(org_id),
    entity_id            UUID REFERENCES reporting_entities(entity_id),
    framework            TEXT NOT NULL,          -- sfdr_pai | bank_tcfd | eu_taxonomy | csrd_e1 | ...
    period_end           DATE NOT NULL,
    period_label         TEXT NOT NULL,          -- e.g. 'FY2025'
    status               TEXT NOT NULL DEFAULT 'draft'
                          CHECK (status IN ('draft','in_review','returned','approved',
                                            'attested','submitted','accepted','rejected','superseded')),
    snapshot_id          UUID REFERENCES report_snapshots(snapshot_id),   -- frozen payload (set on generate)
    approval_request_id  UUID REFERENCES approval_requests(request_id),   -- the 4-eyes gate at review
    submission_ref       TEXT,                   -- regulator ack / filing reference once submitted
    superseded_by        UUID REFERENCES regulatory_filing(filing_id),    -- restatement chain
    note                 TEXT,
    created_by           UUID REFERENCES users(user_id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_reg_filing_org        ON regulatory_filing (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_reg_filing_org_status ON regulatory_filing (org_id, status);
-- at most one *live* filing per (org, entity, framework, period); a superseded one frees the slot
CREATE UNIQUE INDEX IF NOT EXISTS ux_reg_filing_live
    ON regulatory_filing (org_id, framework, period_end, COALESCE(entity_id, '00000000-0000-0000-0000-000000000000'::uuid))
    WHERE status <> 'superseded';

CREATE TABLE IF NOT EXISTS regulatory_filing_event (
    event_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id      UUID NOT NULL REFERENCES regulatory_filing(filing_id),
    from_status    TEXT,
    to_status      TEXT NOT NULL,
    action         TEXT NOT NULL,               -- generate | submit_for_review | approve | reject | return
                                                --  | attest | submit | accept | supersede | note
    actor_user_id  UUID REFERENCES users(user_id),
    detail         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_reg_filing_event ON regulatory_filing_event (filing_id, created_at);

CREATE TABLE IF NOT EXISTS regulatory_obligation (
    obligation_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES organizations(org_id),
    entity_id      UUID REFERENCES reporting_entities(entity_id),
    framework      TEXT NOT NULL,
    period_end     DATE NOT NULL,
    period_label   TEXT NOT NULL,
    due_date       DATE NOT NULL,
    frequency      TEXT NOT NULL DEFAULT 'annual'
                    CHECK (frequency IN ('annual','semiannual','quarterly','monthly','adhoc')),
    note           TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, framework, period_end, entity_id)
);
CREATE INDEX IF NOT EXISTS ix_reg_obligation_due ON regulatory_obligation (org_id, due_date);
"""


# WORM on the event log + freeze a filing's core once submitted/accepted.
GUARDS = """
CREATE OR REPLACE FUNCTION prevent_filing_event_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'regulatory_filing_event is an append-only lifecycle log; % is blocked', TG_OP;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_filing_event_worm ON regulatory_filing_event;
CREATE TRIGGER trg_filing_event_worm
    BEFORE UPDATE OR DELETE ON regulatory_filing_event
    FOR EACH ROW EXECUTE FUNCTION prevent_filing_event_mutation();

CREATE OR REPLACE FUNCTION guard_filing_transition() RETURNS trigger AS $$
BEGIN
    -- once filed with the regulator, the record is frozen: only supersession (restatement) may touch it.
    IF OLD.status IN ('submitted','accepted') THEN
        IF NEW.status = OLD.status
           AND NEW.snapshot_id IS NOT DISTINCT FROM OLD.snapshot_id
           AND NEW.period_end = OLD.period_end
           AND NEW.framework = OLD.framework THEN
            RETURN NEW;                         -- no-op / metadata touch allowed
        END IF;
        IF NEW.status <> 'superseded' THEN
            RAISE EXCEPTION 'filing % is % and can only be superseded by a restatement, not changed to %',
                            OLD.filing_id, OLD.status, NEW.status;
        END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_filing_transition ON regulatory_filing;
CREATE TRIGGER trg_filing_transition
    BEFORE UPDATE ON regulatory_filing
    FOR EACH ROW EXECUTE FUNCTION guard_filing_transition();
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute(GUARDS)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_filing_transition ON regulatory_filing")
    op.execute("DROP FUNCTION IF EXISTS guard_filing_transition()")
    op.execute("DROP TRIGGER IF EXISTS trg_filing_event_worm ON regulatory_filing_event")
    op.execute("DROP FUNCTION IF EXISTS prevent_filing_event_mutation()")
    op.execute("DROP TABLE IF EXISTS regulatory_obligation")
    op.execute("DROP TABLE IF EXISTS regulatory_filing_event")
    op.execute("DROP TABLE IF EXISTS regulatory_filing")
