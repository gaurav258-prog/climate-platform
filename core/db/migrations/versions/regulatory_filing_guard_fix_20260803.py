"""Fix the filing freeze-guard: a submitted filing may still move forward to accepted / superseded.

The first cut froze a filing so hard that the legitimate submitted → accepted transition (recording the
regulator's acknowledgement) was blocked. The real intent is narrower: once submitted, the *content* is
frozen (snapshot, period, framework can't change) and the status can only move FORWARD — to accepted, or to
superseded by a restatement. This replaces the guard function to encode exactly that.

Revision ID: reg_filing_guard_fix_20260803
Revises: regulatory_filings_20260803
"""
from alembic import op

revision = "reg_filing_guard_fix_20260803"
down_revision = "regulatory_filings_20260803"
branch_labels = None
depends_on = None


FIXED = """
CREATE OR REPLACE FUNCTION guard_filing_transition() RETURNS trigger AS $$
BEGIN
    IF OLD.status IN ('submitted','accepted') THEN
        -- content is frozen once filed
        IF NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id
           OR NEW.period_end <> OLD.period_end
           OR NEW.framework <> OLD.framework THEN
            RAISE EXCEPTION 'filing % is % — its frozen content cannot change (restate via supersession)',
                            OLD.filing_id, OLD.status;
        END IF;
        -- status may only move forward: submitted→accepted, or either→superseded
        IF NEW.status <> OLD.status
           AND NOT (OLD.status = 'submitted' AND NEW.status = 'accepted')
           AND NEW.status <> 'superseded' THEN
            RAISE EXCEPTION 'filing % is % and can only be accepted or superseded, not changed to %',
                            OLD.filing_id, OLD.status, NEW.status;
        END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

ORIGINAL = """
CREATE OR REPLACE FUNCTION guard_filing_transition() RETURNS trigger AS $$
BEGIN
    IF OLD.status IN ('submitted','accepted') THEN
        IF NEW.status = OLD.status
           AND NEW.snapshot_id IS NOT DISTINCT FROM OLD.snapshot_id
           AND NEW.period_end = OLD.period_end
           AND NEW.framework = OLD.framework THEN
            RETURN NEW;
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
"""


def upgrade() -> None:
    op.execute(FIXED)


def downgrade() -> None:
    op.execute(ORIGINAL)
