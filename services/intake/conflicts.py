"""Where the client's value and ours differ — the queue a person works through (intake phase 3).

Principle 1 (agreed 2026-09-25): the client wins on facts about their own assets; our value is kept alongside and a
real difference is flagged. So the live value stays the client's until a person decides:

  client      keep the client's value (the default) — the decision is recorded, the conflict closes
  explained   the difference is understood and noted (e.g. an asset on a border) — closes, value unchanged
  tellumen    use our value — a second person approves (approval type intake.conflict), then the live value changes
  agreed      set by the system when the two values come to agree (a corrected file, a moved asset)

A decision stands: the same pair of values (client, ours) is never raised again; a NEW value from either side is.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intake import observations as O


class ConflictError(ValueError):
    pass


def reconcile(session: Session, org_id: str, table: str, asset_ids: list[str]) -> dict:
    """Compare the latest client and Tellumen statement of every derived fact of these assets."""
    seen = O.latest(session, org_id, table, asset_ids)
    open_rows = {(r["asset_id"], r["field"]): dict(r) for r in session.execute(text("""
        SELECT conflict_id::text, asset_id::text, field, status, client_value, tellumen_value FROM asset_conflicts
        WHERE asset_table = :t AND asset_id = ANY(CAST(:ids AS uuid[])) AND status <> 'resolved'
    """), {"t": table, "ids": asset_ids}).mappings().all()}
    decided = {(r["asset_id"], r["field"], json.dumps(r["client_value"]), json.dumps(r["tellumen_value"]))
               for r in session.execute(text("""
        SELECT asset_id::text, field, client_value, tellumen_value FROM asset_conflicts
        WHERE asset_table = :t AND asset_id = ANY(CAST(:ids AS uuid[])) AND status = 'resolved' AND resolution <> 'agreed'
    """), {"t": table, "ids": asset_ids}).mappings().all()}
    out = {"opened": 0, "agreed": 0}
    for aid in asset_ids:
        for d in O.DERIVERS:
            c, t = seen.get((aid, d.field, "client")), seen.get((aid, d.field, "tellumen"))
            why = d.differs(c["value"], t["value"]) if c and t else None
            cur = open_rows.get((aid, d.field))
            if why is None:
                if cur is not None and cur["status"] == "open":
                    session.execute(text("""
                        UPDATE asset_conflicts SET status = 'resolved', resolution = 'agreed', resolved_at = now(),
                               note = 'the two values now agree' WHERE conflict_id = CAST(:c AS uuid)
                    """), {"c": cur["conflict_id"]})
                    out["agreed"] += 1
                continue
            pair = (aid, d.field, json.dumps(O.norm(c["value"])), json.dumps(O.norm(t["value"])))
            if cur is not None:
                if cur["status"] == "open" and (not O.same(cur["client_value"], c["value"]) or not O.same(cur["tellumen_value"], t["value"])):
                    session.execute(text("""
                        UPDATE asset_conflicts SET client_observation_id = :co, tellumen_observation_id = :to,
                               client_value = CAST(:cv AS jsonb), tellumen_value = CAST(:tv AS jsonb), rule = :r
                        WHERE conflict_id = CAST(:c AS uuid)
                    """), {"co": c["observation_id"], "to": t["observation_id"], "cv": pair[2], "tv": pair[3], "r": why,
                           "c": cur["conflict_id"]})
                continue
            if pair in decided:
                continue                                   # a person already decided this exact difference
            session.execute(text("""
                INSERT INTO asset_conflicts (org_id, asset_table, asset_id, field, client_observation_id, tellumen_observation_id,
                                             client_value, tellumen_value, rule)
                VALUES (CAST(:o AS uuid), :t, CAST(:a AS uuid), :f, :co, :to, CAST(:cv AS jsonb), CAST(:tv AS jsonb), :r)
            """), {"o": org_id, "t": table, "a": aid, "f": d.field, "co": c["observation_id"], "to": t["observation_id"],
                   "cv": pair[2], "tv": pair[3], "r": why})
            out["opened"] += 1
    return out


def _name_sql(table: str) -> str:
    col = {b.table: b.name_column for b in O.books()}[table]
    id_col = {b.table: b.id_column for b in O.books()}[table]
    return f"(SELECT {col} FROM {table} x WHERE x.{id_col} = c.asset_id)"


def list_conflicts(session: Session, org_id: str, status: str = "open", limit: int = 200) -> dict:
    tables = sorted({b.table for b in O.books()})
    name = "CASE c.asset_table " + " ".join(f"WHEN '{t}' THEN {_name_sql(t)}" for t in tables) + " END"
    where = "c.status <> 'resolved'" if status == "open" else "c.status = 'resolved'"
    rows = session.execute(text(f"""
        SELECT c.conflict_id::text, c.asset_table, c.asset_id::text, {name} AS asset_name, c.field, c.client_value,
               c.tellumen_value, c.rule, c.status, c.resolution, c.note, c.created_at, c.resolved_at,
               c.approval_request_id::text AS approval_request_id
        FROM asset_conflicts c WHERE c.org_id = CAST(:o AS uuid) AND {where}
        ORDER BY c.seq DESC LIMIT :n
    """), {"o": org_id, "n": limit}).mappings().all()
    counts = dict(session.execute(text("""
        SELECT status, count(*) FROM asset_conflicts WHERE org_id = CAST(:o AS uuid) GROUP BY status
    """), {"o": org_id}).all())
    derivers = [{"field": d.field, "method": d.method, "source": d.origin} for d in O.DERIVERS]
    return {"conflicts": [{**dict(r), "created_at": r["created_at"].isoformat(),
                           "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
                           "why_ours": O.deriver_for(r["field"]).origin if O.deriver_for(r["field"]) else None} for r in rows],
            "counts": {k: int(v) for k, v in counts.items()}, "tellumen_checks": derivers}


def _get(session: Session, org_id: str, conflict_id: str) -> dict:
    r = session.execute(text("SELECT * FROM asset_conflicts WHERE conflict_id = CAST(:c AS uuid) AND org_id = CAST(:o AS uuid)"),
                        {"c": conflict_id, "o": org_id}).mappings().first()
    if not r:
        raise ConflictError("conflict not found")
    return dict(r)


def resolve(session: Session, org_id: str, conflict_id: str, decision: str, actor_user_id: str, note: Optional[str]) -> dict:
    """keep the client's value / explain it (applied now) — or ask to use ours (a second person approves)."""
    from api.services.rbac import write_audit
    c = _get(session, org_id, conflict_id)
    if c["status"] != "open":
        raise ConflictError(f"this conflict is {c['status'].replace('_', ' ')}, not open")
    note = (note or "").strip() or None
    if decision == "explained" and not note:
        raise ConflictError("say what explains the difference")
    if decision in ("client", "explained"):
        session.execute(text("""
            UPDATE asset_conflicts SET status = 'resolved', resolution = :d, note = :n, resolved_by = CAST(:u AS uuid),
                   resolved_at = now() WHERE conflict_id = CAST(:c AS uuid)
        """), {"d": decision, "n": note, "u": actor_user_id, "c": conflict_id})
        write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action=f"intake.conflict.{decision}",
                    target_type="asset_conflict", target_id=conflict_id, detail={"field": c["field"], "note": note})
        return {"conflict_id": conflict_id, "status": "resolved", "resolution": decision}
    if decision != "tellumen":
        raise ConflictError("decide client, tellumen or explained")
    payload = {"conflict_id": conflict_id, "asset_table": c["asset_table"], "asset_id": str(c["asset_id"]), "field": c["field"],
               "client_value": c["client_value"], "tellumen_value": c["tellumen_value"], **({"note": note} if note else {})}
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (CAST(:o AS uuid), 'intake.conflict', :ti, CAST(:p AS jsonb), CAST(:m AS uuid)) RETURNING request_id
    """), {"o": org_id, "ti": f"Use Tellumen's {c['field']} ({c['tellumen_value']}) instead of the client's ({c['client_value']})",
           "p": json.dumps(payload, default=str), "m": actor_user_id}).scalar()
    session.execute(text("""
        UPDATE asset_conflicts SET status = 'awaiting_approval', approval_request_id = CAST(:r AS uuid), note = :n
        WHERE conflict_id = CAST(:c AS uuid)
    """), {"r": str(rid), "n": note, "c": conflict_id})
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="approval.create", target_type="approval",
                target_id=str(rid), detail={"request_type": "intake.conflict", "conflict_id": conflict_id})
    return {"conflict_id": conflict_id, "status": "awaiting_approval", "approval_request_id": str(rid)}


def apply_decision(session: Session, org_id: str, payload: dict, decision: str, checker_user_id: str) -> dict:
    """The checker's decision on using our value. Approved → the live value becomes ours; rejected → the conflict reopens."""
    c = _get(session, org_id, payload["conflict_id"])
    if c["status"] != "awaiting_approval":
        return {"applied": False, "reason": f"conflict is {c['status']}"}
    if decision != "approved":
        session.execute(text("UPDATE asset_conflicts SET status = 'open', approval_request_id = NULL WHERE conflict_id = CAST(:c AS uuid)"),
                        {"c": payload["conflict_id"]})
        return {"applied": False, "conflict": "reopened"}
    book = next((b for b in O.book_for(c["asset_table"]) if c["field"] in b.fields), None)
    if book is None or O.deriver_for(c["field"]) is None:                  # field names come from the registry, never input
        raise ConflictError(f"{c['field']} is not a fact Tellumen derives")
    session.execute(text(f"UPDATE {book.table} SET {c['field']} = :v WHERE {book.id_column} = CAST(:a AS uuid) AND org_id = CAST(:o AS uuid)"),
                    {"v": O.norm(c["tellumen_value"]), "a": str(c["asset_id"]), "o": org_id})
    session.execute(text("""
        UPDATE asset_conflicts SET status = 'resolved', resolution = 'tellumen', resolved_by = CAST(:u AS uuid), resolved_at = now()
        WHERE conflict_id = CAST(:c AS uuid)
    """), {"u": checker_user_id, "c": payload["conflict_id"]})
    return {"applied": True, "field": c["field"], "value": c["tellumen_value"]}
