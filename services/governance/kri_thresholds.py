"""KRI appetite thresholds — resolve a per-org RAG band for each KRI and grade a value against it.

An org's row overrides the platform default (org_id NULL). A KRI graded against its band gets a status —
`ok` / `amber` / `red` (or None when no band is set). `direction` says which way is bad: `higher_worse`
(e.g. share at risk, loss ratio) trips amber/red as the value RISES; `lower_worse` (e.g. coverage) trips as
it FALLS. This is the layer that turns a displayed number into a monitored control.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

_FIELDS = ("amber", "red", "direction")


def thresholds(session: Session, org_id: str, framework: str) -> dict:
    """The org's effective bands for a framework (its rows over the platform defaults), keyed by kri_key."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (kri_key) kri_key, amber, red, direction, (org_id IS NOT NULL) AS org_override
        FROM kri_threshold
        WHERE framework = :fw AND (org_id = :o OR org_id IS NULL)
        ORDER BY kri_key, org_id NULLS LAST
    """), {"fw": framework, "o": org_id}).mappings().all()
    return {r["kri_key"]: dict(r) for r in rows}


def grade(value, band: dict | None) -> str | None:
    """ok / amber / red for a value against a band, or None if ungraded (no band, or non-numeric value)."""
    if not band or value is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    amber, red, direction = band.get("amber"), band.get("red"), band.get("direction", "higher_worse")
    if amber is None and red is None:
        return None                                   # both edges cleared → the KRI is shown but ungraded
    if direction == "lower_worse":
        if red is not None and value <= red:
            return "red"
        if amber is not None and value <= amber:
            return "amber"
        return "ok"
    # higher_worse (default)
    if red is not None and value >= red:
        return "red"
    if amber is not None and value >= amber:
        return "amber"
    return "ok"


def apply(session: Session, org_id: str, framework: str, kpis: list[dict]) -> None:
    """Grade each KPI in place against the org's bands — attaches status/amber/red/direction/breached."""
    bands = thresholds(session, org_id, framework)
    for k in kpis:
        band = bands.get(k.get("key"))
        if not band:
            continue
        status = grade(k.get("value"), band)
        k["status"] = status
        k["amber"] = band.get("amber")
        k["red"] = band.get("red")
        k["direction"] = band.get("direction")
        k["breached"] = status in ("amber", "red")


def set_threshold(session: Session, org_id: str, actor: str, framework: str, kri_key: str, patch: dict, *,
                  reason: str | None = None, approved_by: str | None = None, approval_request_id: str | None = None) -> dict:
    """Upsert the org's band for one KRI and record the change as the next version of that band (who, why, what
    it replaced, and — when the approval matrix required it — who approved). A null amber AND red clears the
    band (leaves the KRI ungraded)."""
    cur = thresholds(session, org_id, framework).get(kri_key, {})
    merged = {f: patch.get(f, cur.get(f)) for f in _FIELDS}
    direction = merged["direction"] if merged["direction"] in ("higher_worse", "lower_worse") else "higher_worse"
    version = (session.execute(text("SELECT COALESCE(max(version), 0) FROM kri_threshold_version WHERE org_id = :o AND framework = :fw AND kri_key = :k"),
                               {"o": org_id, "fw": framework, "k": kri_key}).scalar() or 0) + 1
    session.execute(text("""
        INSERT INTO kri_threshold_version (org_id, framework, kri_key, version, amber, red, direction, previous, reason, changed_by, approved_by, approval_request_id)
        VALUES (CAST(:o AS uuid), :fw, :k, :v, :a, :r, :d, CAST(:prev AS jsonb), :why, CAST(:u AS uuid), CAST(:ap AS uuid), CAST(:req AS uuid))
    """), {"o": org_id, "fw": framework, "k": kri_key, "v": version, "a": merged["amber"], "r": merged["red"], "d": direction,
           "prev": json.dumps({f: (float(cur[f]) if isinstance(cur.get(f), (int, float)) and f != "direction" else cur.get(f)) for f in _FIELDS if f in cur}, default=str) if cur else None,
           "why": (reason or "").strip() or None, "u": actor, "ap": approved_by, "req": approval_request_id})
    session.execute(text("""
        INSERT INTO kri_threshold (org_id, framework, kri_key, amber, red, direction, updated_by, updated_at)
        VALUES (:o, :fw, :k, :a, :r, :d, :u, now())
        ON CONFLICT (org_id, framework, kri_key) WHERE org_id IS NOT NULL
        DO UPDATE SET amber = EXCLUDED.amber, red = EXCLUDED.red, direction = EXCLUDED.direction,
                      updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"o": org_id, "fw": framework, "k": kri_key, "a": merged["amber"], "r": merged["red"],
           "d": direction, "u": actor})
    return thresholds(session, org_id, framework).get(kri_key, {})


def history(session: Session, org_id: str, framework: str, kri_key: str | None = None, limit: int = 100) -> list[dict]:
    """The version history of the org's appetite bands — the appetite statement's audit trail."""
    rows = session.execute(text(f"""
        SELECT v.framework, v.kri_key, v.version, v.amber, v.red, v.direction, v.previous, v.reason, v.created_at, v.approval_request_id::text AS approval_request_id,
               cu.full_name AS changed_by, au.full_name AS approved_by
        FROM kri_threshold_version v LEFT JOIN users cu ON cu.user_id = v.changed_by LEFT JOIN users au ON au.user_id = v.approved_by
        WHERE v.org_id = CAST(:o AS uuid) AND v.framework = :fw {"AND v.kri_key = :k" if kri_key else ""} ORDER BY v.created_at DESC LIMIT :l
    """), {"o": org_id, "fw": framework, "k": kri_key, "l": limit}).mappings().all()
    return [dict(r) | {"amber": float(r["amber"]) if r["amber"] is not None else None, "red": float(r["red"]) if r["red"] is not None else None, "created_at": r["created_at"].isoformat()} for r in rows]
