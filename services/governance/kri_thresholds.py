"""KRI appetite thresholds — resolve a per-org RAG band for each KRI and grade a value against it.

An org's row overrides the platform default (org_id NULL). A KRI graded against its band gets a status —
`ok` / `amber` / `red` (or None when no band is set). `direction` says which way is bad: `higher_worse`
(e.g. share at risk, loss ratio) trips amber/red as the value RISES; `lower_worse` (e.g. coverage) trips as
it FALLS. This is the layer that turns a displayed number into a monitored control.
"""
from __future__ import annotations

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


def set_threshold(session: Session, org_id: str, actor: str, framework: str, kri_key: str, patch: dict) -> dict:
    """Upsert the org's band for one KRI. A null amber AND red clears the band (leaves the KRI ungraded)."""
    cur = thresholds(session, org_id, framework).get(kri_key, {})
    merged = {f: patch.get(f, cur.get(f)) for f in _FIELDS}
    direction = merged["direction"] if merged["direction"] in ("higher_worse", "lower_worse") else "higher_worse"
    session.execute(text("""
        INSERT INTO kri_threshold (org_id, framework, kri_key, amber, red, direction, updated_by, updated_at)
        VALUES (:o, :fw, :k, :a, :r, :d, :u, now())
        ON CONFLICT (org_id, framework, kri_key) WHERE org_id IS NOT NULL
        DO UPDATE SET amber = EXCLUDED.amber, red = EXCLUDED.red, direction = EXCLUDED.direction,
                      updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"o": org_id, "fw": framework, "k": kri_key, "a": merged["amber"], "r": merged["red"],
           "d": direction, "u": actor})
    return thresholds(session, org_id, framework).get(kri_key, {})
