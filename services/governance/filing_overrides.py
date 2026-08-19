"""Cell-level manual overrides on the final form — proposed with a reason, approved by a second pair of eyes
(routed through the shared approval_requests 4-eyes), then merged over the immutable snapshot at read time.

The frozen snapshot is never mutated: an approved override is a separate record that carries the original
calculated value + who/when/why, so the manual change is always distinguishable and fully auditable.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


class OverrideError(ValueError):
    pass


def _filing_form(session: Session, org_id: str, filing_id: str):
    """(framework, raw datapoints-by-key) for a filing's frozen snapshot — the calculated baseline."""
    from services.governance.filing_form import build_form
    r = session.execute(text("""
        SELECT rf.framework, s.payload FROM regulatory_filing rf
        LEFT JOIN report_snapshots s ON s.snapshot_id = rf.snapshot_id
        WHERE rf.org_id = :o AND rf.filing_id = :f
    """), {"o": org_id, "f": filing_id}).mappings().first()
    if not r:
        return None, {}
    dps = {d["key"]: d for g in build_form(r["framework"], r["payload"] or {}) for d in g["datapoints"]}
    return r["framework"], dps


def propose(session: Session, org_id: str, filing_id: str, actor: str, *, datapoint_key: str,
            value: float, reason: str) -> dict:
    if not (reason or "").strip():
        raise OverrideError("a reason is required for a manual override")
    framework, dps = _filing_form(session, org_id, filing_id)
    if framework is None:
        raise OverrideError("filing not found")
    dp = dps.get(datapoint_key)
    if not dp:
        raise OverrideError("unknown datapoint")
    if dp["fmt"] == "text" or not isinstance(dp["value"], (int, float)):
        raise OverrideError("this datapoint can't be overridden numerically")
    original = dp["value"]

    # one live override per (filing, datapoint) — a new proposal supersedes any prior pending/approved one
    session.execute(text("""
        UPDATE filing_cell_override SET status = 'superseded'
        WHERE filing_id = :f AND datapoint_key = :k AND status IN ('pending','approved')
    """), {"f": filing_id, "k": datapoint_key})

    oid = session.execute(text("""
        INSERT INTO filing_cell_override (org_id, filing_id, datapoint_key, original_value, proposed_value, reason, proposed_by)
        VALUES (:o, :f, :k, :ov, :pv, :r, :u) RETURNING override_id
    """), {"o": org_id, "f": filing_id, "k": datapoint_key, "ov": original, "pv": value, "r": reason.strip(), "u": actor}).scalar()

    # raise the 4-eyes request through the shared machinery (checker ≠ maker enforced by the approvals router)
    import json
    payload = {"filing_id": filing_id, "override_id": str(oid), "datapoint_key": datapoint_key,
               "label": dp["label"], "from": original, "to": value}
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (:o, 'filing.cell_override', :ti, CAST(:p AS jsonb), :m) RETURNING request_id
    """), {"o": org_id, "ti": f"Manual override · {dp['label']}", "p": json.dumps(payload), "m": actor}).scalar()
    session.execute(text("UPDATE filing_cell_override SET approval_request_id = :r WHERE override_id = :oid"),
                    {"r": rid, "oid": oid})
    return {"override_id": str(oid), "status": "pending", "approval_request_id": str(rid)}


def apply_decision(session: Session, org_id: str, payload: dict, decision: str, actor: str) -> dict:
    """Called from the approvals decide handler when a filing.cell_override request is decided."""
    oid = (payload or {}).get("override_id")
    status = "approved" if decision == "approved" else "rejected"
    session.execute(text("""
        UPDATE filing_cell_override SET status = :s, decided_by = :u, decided_at = now()
        WHERE override_id = :oid AND org_id = :o AND status = 'pending'
    """), {"s": status, "u": actor, "oid": oid, "o": org_id})
    return {"override_id": oid, "status": status}


def overrides_for_filing(session: Session, org_id: str, filing_id: str) -> dict:
    """datapoint_key -> the live override (pending or approved) with its provenance, for merge + display."""
    rows = session.execute(text("""
        SELECT o.datapoint_key, o.status, o.original_value::float AS original_value,
               o.proposed_value::float AS proposed_value, o.reason, o.proposed_at, o.decided_at,
               pu.email AS proposed_by, du.email AS decided_by
        FROM filing_cell_override o
        LEFT JOIN users pu ON pu.user_id = o.proposed_by
        LEFT JOIN users du ON du.user_id = o.decided_by
        WHERE o.org_id = :o AND o.filing_id = :f AND o.status IN ('pending','approved')
        ORDER BY o.proposed_at DESC
    """), {"o": org_id, "f": filing_id}).mappings().all()
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["datapoint_key"], {  # newest per key (ordered DESC)
            "status": r["status"], "original_value": r["original_value"], "proposed_value": r["proposed_value"],
            "reason": r["reason"], "proposed_by": r["proposed_by"], "decided_by": r["decided_by"],
            "proposed_at": r["proposed_at"].isoformat() if r["proposed_at"] else None,
            "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None,
        })
    return out
