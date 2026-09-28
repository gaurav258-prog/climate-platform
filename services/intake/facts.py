"""One asset's facts, per source: what the engine reads (live), what the client stated, what we derive, and the history
of each — the asset-level view of intake phase 3."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intake import observations as O


def asset_facts(session: Session, org_id: str, table: str, asset_id: str) -> dict:
    books = O.book_for(table)
    if not books:
        raise ValueError(f"'{table}' is not an asset book")
    row, book = None, None
    for b in books:
        row = next((r for r in b.load(session, org_id) if r["entity_id"] == asset_id), None)
        if row:
            book = b
            break
    if row is None:
        raise ValueError("asset not found")
    seen = O.latest(session, org_id, table, [asset_id])
    open_c = {r["field"]: dict(r) for r in session.execute(text("""
        SELECT conflict_id::text, field, rule, status FROM asset_conflicts
        WHERE asset_table = :t AND asset_id = CAST(:a AS uuid) AND status <> 'resolved'
    """), {"t": table, "a": asset_id}).mappings().all()}

    def stated(src, f):
        s = seen.get((asset_id, f, src))
        return None if s is None else {"value": s["value"], "method": s["method"], "origin": s["origin"],
                                       "observed_at": s["observed_at"].isoformat()}

    fields = []
    for f in book.fields:
        d = O.deriver_for(f)
        c, t = stated("client", f), stated("tellumen", f)
        fields.append({"field": f, "live": O.norm(row.get(f)), "client": c, "tellumen": t,
                       "tellumen_check": d.origin if d else None,
                       "live_is": ("client" if c and O.same(c["value"], row.get(f)) else
                                   "tellumen" if t and O.same(t["value"], row.get(f)) else None),
                       "conflict": open_c.get(f)})
    return {"asset_table": table, "asset_id": asset_id, "name": row.get(book.name_column), "book": book.key,
            "fields": fields, "history": O.history(session, org_id, table, asset_id)}
