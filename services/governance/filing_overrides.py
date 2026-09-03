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
    """Called from the approvals decide handler when a filing.cell_override request is decided.

    Two shapes share this handler: a datapoint override (`override_id`) and a GRID-cell manual entry
    (`grid: true`) — a value typed into an 'integrated' (bank-fed) grid cell that has no connected feed yet.
    Both are 4-eyes-gated; only on APPROVAL is the value written to the served form (the grid value lands in
    the org's manual-cell overlay `p3esg_narratives.cells`, the same layer the form already renders)."""
    payload = payload or {}
    if payload.get("grid"):
        cell_key = payload.get("cell_key")
        if decision == "approved":
            cur = _org_cells(session, org_id)
            cells = dict(cur.get("cells") or {})
            val = (payload.get("value") or "").strip()
            if val:
                cells[cell_key] = val
            else:
                cells.pop(cell_key, None)     # an approved clear reverts the cell to the fed '—'
            cur["cells"] = cells
            _save_org_cells(session, org_id, cur)
        return {"grid": True, "cell_key": cell_key, "status": decision}

    oid = payload.get("override_id")
    status = "approved" if decision == "approved" else "rejected"
    session.execute(text("""
        UPDATE filing_cell_override SET status = :s, decided_by = :u, decided_at = now()
        WHERE override_id = :oid AND org_id = :o AND status = 'pending'
    """), {"s": status, "u": actor, "oid": oid, "o": org_id})
    return {"override_id": oid, "status": status}


# ── Grid-cell manual entry (task #56): typing a value into an 'integrated' grid cell needs the SAME 4-eyes as a
#    datapoint override, not a silent direct write. Pending state lives on approval_requests; the APPROVED value
#    lands in the org's manual-cell overlay (p3esg_narratives.cells), which the Pillar 3 form already renders. ──
_GRID_REQUEST_TYPE = "filing.cell_override"   # reuse the shared 4-eyes handler; payload.grid distinguishes it


def _org_cells(session: Session, org_id: str) -> dict:
    import json as _json
    row = session.execute(text("SELECT p3esg_narratives FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                          {"o": org_id}).scalar()
    return (_json.loads(row) if isinstance(row, str) else row) or {}


def _save_org_cells(session: Session, org_id: str, cur: dict) -> None:
    import json as _json
    session.execute(text("UPDATE organizations SET p3esg_narratives = CAST(:n AS jsonb) WHERE org_id = CAST(:o AS uuid)"),
                    {"n": _json.dumps(cur), "o": org_id})


def propose_grid_cell(session: Session, org_id: str, actor: str, *, cell_key: str, value: str, reason: str) -> dict:
    """Propose a manual value for an integrated grid cell (or clear it, value=''). Raises a 4-eyes request;
    the value only appears on the form once a second person approves it. One live proposal per cell."""
    import json as _json
    if not (reason or "").strip():
        raise OverrideError("a reason is required for a manual cell entry")
    if not (cell_key or "").strip():
        raise OverrideError("cell key is required")
    value = (value or "").strip()

    # supersede any prior pending proposal for the same cell so the approvals queue stays one-per-cell
    session.execute(text("""
        UPDATE approval_requests SET status = 'rejected', reason = 'superseded by a newer entry', decided_at = now()
        WHERE org_id = CAST(:o AS uuid) AND request_type = :rt AND status = 'pending'
          AND (payload->>'grid') = 'true' AND (payload->>'cell_key') = :k
    """), {"o": org_id, "rt": _GRID_REQUEST_TYPE, "k": cell_key})

    original = (_org_cells(session, org_id).get("cells") or {}).get(cell_key)
    payload = {"grid": True, "cell_key": cell_key, "value": value, "reason": reason.strip(),
               "from": original, "label": cell_key}
    action = "clear" if value == "" else "entry"
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (CAST(:o AS uuid), :rt, :ti, CAST(:p AS jsonb), :m) RETURNING request_id
    """), {"o": org_id, "rt": _GRID_REQUEST_TYPE, "ti": f"Manual grid-cell {action} · {cell_key}",
           "p": _json.dumps(payload), "m": actor}).scalar()
    return {"status": "pending", "approval_request_id": str(rid), "cell_key": cell_key}


def pending_grid_cells(session: Session, org_id: str) -> dict:
    """cell_key -> the live PENDING manual entry (proposed value + who/why), for the form to show 'awaiting 4-eyes'."""
    rows = session.execute(text("""
        SELECT ar.request_id, ar.payload, ar.created_at, u.email AS maker
        FROM approval_requests ar LEFT JOIN users u ON u.user_id = ar.maker_user_id
        WHERE ar.org_id = CAST(:o AS uuid) AND ar.request_type = :rt AND ar.status = 'pending'
          AND (ar.payload->>'grid') = 'true'
        ORDER BY ar.created_at DESC
    """), {"o": org_id, "rt": _GRID_REQUEST_TYPE}).mappings().all()
    out: dict[str, dict] = {}
    for r in rows:
        p = r["payload"] or {}
        k = p.get("cell_key")
        if k and k not in out:                # newest per cell (ordered DESC)
            out[k] = {"value": p.get("value"), "reason": p.get("reason"),
                      "request_id": str(r["request_id"]), "proposed_by": r["maker"],
                      "proposed_at": r["created_at"].isoformat() if r["created_at"] else None}
    return out


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
