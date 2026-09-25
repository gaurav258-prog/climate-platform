"""Read side of the intake ledger: the batch list and one batch with its full history and staged rows."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_batches(session: Session, org_id: str, limit: int = 50) -> list[dict]:
    rows = session.execute(text("""
        SELECT b.batch_id::text, b.template, b.via, b.filename, b.received_at, b.state, b.state_changed_at, b.n_total,
               b.n_valid, b.n_rejected, b.gate_status, b.rejected_reason, b.approval_request_id::text,
               f.security_status, f.malware_status, (b.landing->>'n_dropped_after_validation')::int AS n_dropped,
               b.match_summary
        FROM ingest_batches b LEFT JOIN intake_files f ON f.file_id = b.file_id
        WHERE b.org_id = CAST(:o AS uuid) ORDER BY b.received_at DESC LIMIT :l
    """), {"o": org_id, "l": limit}).mappings().all()
    out = []
    for r in rows:
        d = {**dict(r), "received_at": str(r["received_at"])[:19], "state_changed_at": str(r["state_changed_at"])[:19]}
        ms = d.pop("match_summary") or {}
        d["matching"] = {k: ms.get(k) for k in ("new", "update", "unchanged")} if ms else None
        out.append(d)
    return out


def get_batch(session: Session, org_id: str, batch_id: str, staged_limit: int = 500) -> Optional[dict]:
    r = session.execute(text("""
        SELECT b.*, b.batch_id::text AS batch_id, b.mapping_profile_id::text AS mapping_profile_id,
               f.sha256 AS file_sha256, f.size_bytes, f.detected_type, f.security_status,
               f.security_findings, f.malware_status, f.malware_signature, f.malware_engine, f.storage_uri, f.retain_until
        FROM ingest_batches b LEFT JOIN intake_files f ON f.file_id = b.file_id
        WHERE b.org_id = CAST(:o AS uuid) AND b.batch_id = CAST(:b AS uuid)
    """), {"o": org_id, "b": batch_id}).mappings().first()
    if not r:
        return None
    d = dict(r)
    d["events"] = [{**dict(e), "at": str(e["at"])[:19]} for e in session.execute(text("""
        SELECT from_state, to_state, at, actor_user_id::text, actor_token_id::text, detail FROM ingest_batch_events
        WHERE batch_id = CAST(:b AS uuid) ORDER BY at
    """), {"b": batch_id}).mappings().all()]
    d["staged"] = [dict(s) for s in session.execute(text("""
        SELECT row_no, status, record, problems, match_status, target_entity_id::text AS target_entity_id, diff
        FROM intake_staged_records WHERE batch_id = CAST(:b AS uuid) ORDER BY row_no LIMIT :l
    """), {"b": batch_id, "l": staged_limit}).mappings().all()]
    return d
