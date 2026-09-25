"""Customer data intake pipeline — phase 1: received files, security results, batch states, 4-eyes approval.

  * intake_files — every file (or API payload) exactly as received: fingerprint, size, real type, where it is
    stored (write-once), the static security inspection and the malware-scan result. Its identity can never
    change; only a held file's scan result can be filled in later. Never deleted (evidence behind filings).
  * ingest_batch_events — append-only history of every state a batch passes through (who, when, why).
  * ingest_batches — reshaped around a state machine:
        received → held (scanner unavailable, retryable) | rejected (security / nothing valid / approval refused)
                 → checked → awaiting_approval (a check failed: needs a second person) → imported
    The old single-person sign-off columns are replaced by maker_reason + approval_request_id: a batch that
    failed a check can only be imported through an approval_requests row decided by someone other than the maker.

Revision ID: intake_pipeline_20260925
Revises: ingest_batches_20260925
"""
from typing import Sequence, Union

from alembic import op

revision: str = "intake_pipeline_20260925"
down_revision: Union[str, None] = "ingest_batches_20260925"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_files (
            file_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id            UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            sha256            TEXT NOT NULL,
            size_bytes        BIGINT NOT NULL,
            original_name     TEXT,
            detected_type     TEXT NOT NULL,
            storage_uri       TEXT NOT NULL,
            received_via      TEXT NOT NULL,
            received_by       UUID,
            token_id          UUID,
            received_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            security_status   TEXT NOT NULL,
            security_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
            malware_status    TEXT NOT NULL,
            malware_signature TEXT,
            malware_engine    TEXT,
            scanned_at        TIMESTAMPTZ,
            retain_until      DATE NOT NULL,
            CONSTRAINT ck_intake_file_via CHECK (received_via IN ('upload', 'api')),
            CONSTRAINT ck_intake_file_sec CHECK (security_status IN ('passed', 'warned', 'blocked')),
            CONSTRAINT ck_intake_file_mw CHECK (malware_status IN ('clean', 'infected', 'error', 'not_configured', 'not_scanned')),
            CONSTRAINT ck_intake_file_actor CHECK (received_by IS NOT NULL OR token_id IS NOT NULL)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_files_org ON intake_files (org_id, received_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_files_sha ON intake_files (org_id, sha256)")
    op.execute("""
        CREATE OR REPLACE FUNCTION protect_intake_file() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'intake_files is the evidence of what a customer sent; DELETE is blocked';
            END IF;
            IF NEW.sha256 IS DISTINCT FROM OLD.sha256 OR NEW.size_bytes IS DISTINCT FROM OLD.size_bytes
               OR NEW.storage_uri IS DISTINCT FROM OLD.storage_uri OR NEW.org_id IS DISTINCT FROM OLD.org_id
               OR NEW.original_name IS DISTINCT FROM OLD.original_name OR NEW.received_at IS DISTINCT FROM OLD.received_at
               OR NEW.security_findings IS DISTINCT FROM OLD.security_findings THEN
                RAISE EXCEPTION 'intake_files identity and inspection results are immutable; only a scan result may be added';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_intake_file_protect ON intake_files")
    op.execute("CREATE TRIGGER trg_intake_file_protect BEFORE UPDATE OR DELETE ON intake_files "
               "FOR EACH ROW EXECUTE FUNCTION protect_intake_file()")

    # ── reshape ingest_batches (created 2026-09-25, no production rows) ──
    op.execute("ALTER TABLE ingest_batches DROP CONSTRAINT IF EXISTS ck_ingest_batch_signoff")
    op.execute("ALTER TABLE ingest_batches DROP CONSTRAINT IF EXISTS ck_ingest_batch_status")
    op.execute("ALTER TABLE ingest_batches DROP CONSTRAINT IF EXISTS ck_ingest_batch_gate")
    op.execute("""
        ALTER TABLE ingest_batches
            ADD COLUMN IF NOT EXISTS file_id UUID REFERENCES intake_files(file_id),
            ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'received',
            ADD COLUMN IF NOT EXISTS state_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            ADD COLUMN IF NOT EXISTS token_id UUID,
            ADD COLUMN IF NOT EXISTS maker_reason TEXT,
            ADD COLUMN IF NOT EXISTS approval_request_id UUID REFERENCES approval_requests(request_id),
            ADD COLUMN IF NOT EXISTS rejected_reason TEXT,
            ADD COLUMN IF NOT EXISTS ingest_notes JSONB,
            DROP COLUMN IF EXISTS signoff_by,
            DROP COLUMN IF EXISTS signoff_reason,
            DROP COLUMN IF EXISTS status,
            ALTER COLUMN n_total DROP NOT NULL,
            ALTER COLUMN n_valid DROP NOT NULL,
            ALTER COLUMN n_rejected DROP NOT NULL,
            ALTER COLUMN receipt DROP NOT NULL,
            ALTER COLUMN transform DROP NOT NULL,
            ALTER COLUMN gate_status DROP NOT NULL
    """)
    op.execute("""ALTER TABLE ingest_batches ADD CONSTRAINT ck_ingest_batch_state CHECK (state IN
                  ('received', 'held', 'rejected', 'checked', 'awaiting_approval', 'imported'))""")
    op.execute("""ALTER TABLE ingest_batches ADD CONSTRAINT ck_ingest_batch_gate CHECK (gate_status IS NULL OR gate_status IN
                  ('pass', 'needs_signoff', 'blocked'))""")
    # a batch that failed a check can only be imported through an approval by a second person
    op.execute("""ALTER TABLE ingest_batches ADD CONSTRAINT ck_ingest_batch_4eyes CHECK (
                  state <> 'imported' OR gate_status = 'pass' OR approval_request_id IS NOT NULL)""")
    op.execute("""ALTER TABLE ingest_batches ADD CONSTRAINT ck_ingest_batch_awaiting CHECK (
                  state <> 'awaiting_approval' OR approval_request_id IS NOT NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ingest_batches_state ON ingest_batches (org_id, state)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS ingest_batch_events (
            event_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id       UUID NOT NULL REFERENCES ingest_batches(batch_id) ON DELETE CASCADE,
            org_id         UUID NOT NULL,
            at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            from_state     TEXT,
            to_state       TEXT NOT NULL,
            actor_user_id  UUID,
            actor_token_id UUID,
            detail         JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ingest_batch_events ON ingest_batch_events (batch_id, at)")
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_ingest_event_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ingest_batch_events is an append-only history; % is blocked', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_ingest_event_worm ON ingest_batch_events")
    op.execute("CREATE TRIGGER trg_ingest_event_worm BEFORE UPDATE OR DELETE ON ingest_batch_events "
               "FOR EACH ROW EXECUTE FUNCTION prevent_ingest_event_mutation()")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingest_batch_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_ingest_event_mutation()")
    op.execute("ALTER TABLE ingest_batches DROP CONSTRAINT IF EXISTS ck_ingest_batch_4eyes")
    op.execute("ALTER TABLE ingest_batches DROP CONSTRAINT IF EXISTS ck_ingest_batch_awaiting")
    op.execute("ALTER TABLE ingest_batches DROP CONSTRAINT IF EXISTS ck_ingest_batch_state")
    op.execute("""ALTER TABLE ingest_batches DROP COLUMN IF EXISTS file_id, DROP COLUMN IF EXISTS state,
                  DROP COLUMN IF EXISTS state_changed_at, DROP COLUMN IF EXISTS token_id, DROP COLUMN IF EXISTS maker_reason,
                  DROP COLUMN IF EXISTS approval_request_id, DROP COLUMN IF EXISTS rejected_reason, DROP COLUMN IF EXISTS ingest_notes,
                  ADD COLUMN IF NOT EXISTS signoff_by UUID, ADD COLUMN IF NOT EXISTS signoff_reason TEXT,
                  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'accepted'""")
    op.execute("DROP TABLE IF EXISTS intake_files")
    op.execute("DROP FUNCTION IF EXISTS protect_intake_file()")
