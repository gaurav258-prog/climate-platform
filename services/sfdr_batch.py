"""SFDR batch orchestration — generate statements across a manager's whole book.

A manager with hundreds of funds files annually (reference period ends 31 Dec,
filing due 30 Jun). This runs the SFDR PAI statement for every fund, records each
fund's coverage + filing-readiness, and is RESUMABLE: re-running processes only
the funds still pending or errored, so a mid-run failure never loses progress.

Kept broker-independent (plain DB + synchronous loop) so it is testable and can
be driven by an API call, a cron, or wrapped in the existing Celery app for very
large managers without changing this logic.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from ml.regulatory.sfdr_pai import sfdr_pai_statement


def create_batch(session, org_id: str, reference_year: int) -> str:
    """Enumerate the manager's top-level funds and open a batch (all pending)."""
    batch_id = str(session.execute(text("""
        INSERT INTO sfdr_batch_runs (org_id, reference_year) VALUES (:o, :y) RETURNING batch_id
    """), {"o": org_id, "y": reference_year}).scalar())
    funds = session.execute(text("""
        SELECT fund_id::text AS fund_id, name FROM funds
        WHERE org_id = :o AND parent_fund_id IS NULL ORDER BY name
    """), {"o": org_id}).mappings().all()
    for f in funds:
        session.execute(text("""
            INSERT INTO sfdr_batch_items (batch_id, fund_id, fund_name) VALUES (:b, :f, :n)
        """), {"b": batch_id, "f": f["fund_id"], "n": f["name"]})
    session.execute(text("UPDATE sfdr_batch_runs SET total_funds = :n WHERE batch_id = :b"),
                    {"n": len(funds), "b": batch_id})
    return batch_id


def run_batch(session, batch_id: str, limit: Optional[int] = None) -> dict:
    """Process pending/errored items. Resumable: a done item is never recomputed.
    `limit` caps how many funds this invocation processes (for chunked runs)."""
    session.execute(text("UPDATE sfdr_batch_runs SET status='running', updated_at=now() WHERE batch_id=:b"),
                    {"b": batch_id})
    q = """
        SELECT fund_id::text AS fund_id FROM sfdr_batch_items
        WHERE batch_id = :b AND status IN ('pending','error') ORDER BY fund_name
    """
    if limit:
        q += " LIMIT :lim"
    todo = session.execute(text(q), {"b": batch_id, **({"lim": limit} if limit else {})}).scalars().all()

    processed = 0
    for fund_id in todo:
        session.execute(text("UPDATE sfdr_batch_items SET status='running', updated_at=now() "
                             "WHERE batch_id=:b AND fund_id=:f"), {"b": batch_id, "f": fund_id})
        try:
            stmt = sfdr_pai_statement(session, fund_id)
            if stmt.get("error"):
                session.execute(text("""
                    UPDATE sfdr_batch_items SET status='error', error=:e, updated_at=now()
                    WHERE batch_id=:b AND fund_id=:f
                """), {"b": batch_id, "f": fund_id, "e": stmt["error"]})
            else:
                cs = stmt["coverage_summary"]
                session.execute(text("""
                    UPDATE sfdr_batch_items SET status='done', computed=:c, partial=:p, not_available=:n,
                           ready_to_file=:r, error=NULL, updated_at=now()
                    WHERE batch_id=:b AND fund_id=:f
                """), {"b": batch_id, "f": fund_id, "c": cs["computed"], "p": cs["partial"],
                       "n": cs["not_available"], "r": stmt["filing_readiness"]["ready_to_file"]})
        except Exception as e:   # one bad fund must not abort the whole run
            session.execute(text("""
                UPDATE sfdr_batch_items SET status='error', error=:e, updated_at=now()
                WHERE batch_id=:b AND fund_id=:f
            """), {"b": batch_id, "f": fund_id, "e": str(e)[:2000]})
        processed += 1

    remaining = session.execute(text("""
        SELECT count(*) FROM sfdr_batch_items WHERE batch_id=:b AND status IN ('pending','running')
    """), {"b": batch_id}).scalar()
    final = "completed" if remaining == 0 else "running"
    session.execute(text("UPDATE sfdr_batch_runs SET status=:s, updated_at=now() WHERE batch_id=:b"),
                    {"s": final, "b": batch_id})
    return {**batch_status(session, batch_id), "processed_this_run": processed}


def batch_status(session, batch_id: str) -> dict:
    run = session.execute(text("""
        SELECT batch_id::text AS batch_id, org_id::text AS org_id, reference_year, status, total_funds,
               created_at, updated_at FROM sfdr_batch_runs WHERE batch_id = :b
    """), {"b": batch_id}).mappings().first()
    if not run:
        return {"error": "batch not found"}
    counts = dict(session.execute(text("""
        SELECT status, count(*) FROM sfdr_batch_items WHERE batch_id = :b GROUP BY status
    """), {"b": batch_id}).all())
    items = session.execute(text("""
        SELECT fund_id::text AS fund_id, fund_name, status, computed, partial, not_available,
               ready_to_file, error FROM sfdr_batch_items WHERE batch_id = :b ORDER BY fund_name
    """), {"b": batch_id}).mappings().all()
    done = counts.get("done", 0)
    ready = sum(1 for i in items if i["ready_to_file"])
    return {
        "batch_id": run["batch_id"], "org_id": run["org_id"],
        "reference_year": run["reference_year"], "status": run["status"],
        "total_funds": run["total_funds"],
        "progress": {"done": done, "error": counts.get("error", 0),
                     "pending": counts.get("pending", 0), "running": counts.get("running", 0),
                     "ready_to_file": ready},
        "items": [dict(i) for i in items],
    }
