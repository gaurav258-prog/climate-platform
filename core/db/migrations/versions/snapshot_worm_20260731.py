"""Make report_snapshots tamper-evident and re-runnable (audit T1).

A frozen filing promised "the very bytes signed off," but the table stored only the payload — no content
hash (so silent mutation was undetectable) and no engine/data version stamp (so it could be re-read but
not re-run). This adds:
  - `payload_sha256`   — a content hash of the canonical payload, written at freeze time; the assurance
                         pack re-verifies it, so any change to a filed row is detectable.
  - `engine_versions`  — the impact/fit/feed/code versions in force at freeze, so the exact computation
                         behind a filing is identifiable.
  - a WORM trigger      — blocks every UPDATE and DELETE, so "append-only" is enforced in the DB, not only
                         by the service having no update path.

Existing rows are back-filled with a hash BEFORE the trigger is created (the trigger would otherwise block
the back-fill). Canonicalization here MUST match services.governance.report_snapshots._canonical.

Revision ID: snapshot_worm_20260731
Revises: f1_lane_views_20260731
"""
import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "snapshot_worm_20260731"
down_revision = "f1_lane_views_20260731"
branch_labels = None
depends_on = None


def _canonical(obj) -> str:
    # identical to services.governance.report_snapshots._canonical
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def upgrade() -> None:
    op.execute("ALTER TABLE report_snapshots ADD COLUMN IF NOT EXISTS payload_sha256 TEXT")
    op.execute("ALTER TABLE report_snapshots ADD COLUMN IF NOT EXISTS engine_versions JSONB")

    # back-fill hashes for pre-existing snapshots (before the WORM trigger blocks UPDATE)
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT snapshot_id, payload FROM report_snapshots WHERE payload_sha256 IS NULL")).mappings().all()
    for r in rows:
        payload = r["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        conn.execute(sa.text("UPDATE report_snapshots SET payload_sha256 = :h WHERE snapshot_id = :i"),
                     {"h": digest, "i": r["snapshot_id"]})

    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_report_snapshot_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'report_snapshots is an append-only immutable filing record; % is blocked',
                            TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_report_snapshot_worm ON report_snapshots")
    op.execute("""
        CREATE TRIGGER trg_report_snapshot_worm
        BEFORE UPDATE OR DELETE ON report_snapshots
        FOR EACH ROW EXECUTE FUNCTION prevent_report_snapshot_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_report_snapshot_worm ON report_snapshots")
    op.execute("DROP FUNCTION IF EXISTS prevent_report_snapshot_mutation()")
    op.execute("ALTER TABLE report_snapshots DROP COLUMN IF EXISTS engine_versions")
    op.execute("ALTER TABLE report_snapshots DROP COLUMN IF EXISTS payload_sha256")
