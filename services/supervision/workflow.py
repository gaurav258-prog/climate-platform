"""Where each supervised entity stands in the supervisory process — the spine of the Population page.

Five steps, in order, each derived from what the platform actually holds (never a hand-ticked checklist):
  1. submitted   — the entity's expected filings are on record (released statuses only)
  2. ingested    — the supervisor holds the submitted template AND its own granular data for the entity
  3. rebuilt     — the shadow book is built and scenario projections are complete
  4. reviewed    — the independent lens has been run and its questions are on record
  5. engaged     — requests / findings raised with the entity and all of them closed (open ones = partly)
Alongside: the sorting criteria a supervisor uses — sector, jurisdiction, submission coverage, share of book at
high risk (the profile's headline metric), lens gap, site access — and the single next action per entity.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

STEPS = ["submitted", "ingested", "rebuilt", "reviewed", "engaged"]
STEP_LABEL = {"submitted": "Filings received", "ingested": "Data ingested", "rebuilt": "Rebuilt & projected",
              "reviewed": "Reviewed", "engaged": "Engaged"}


def _lens_seen(session, regulator_org_id: str, subject_org_id: str) -> Optional[str]:
    return session.execute(text("""
        SELECT max(created_at) FROM access_audit_log
        WHERE org_id = CAST(:s AS uuid) AND action = 'supervisor.lens.access' AND (detail->>'regulator_org_id') = :r
    """), {"s": subject_org_id, "r": regulator_org_id}).scalar()


def entity_workflow(session, regulator_org_id: str, e: dict, in_profile: bool, submission: Optional[dict],
                    shadow: dict, projection: dict, site_access: bool, headline: Optional[dict], lens_gap_pct: Optional[float],
                    n_flagged: Optional[int]) -> dict:
    """e = population row (with frameworks/filed/expected). Returns steps + stage + next action."""
    from services.supervision.engagement import entity_summary
    eng = entity_summary(session, regulator_org_id, e["org_id"])
    filed_all = e.get("expected", 0) > 0 and e.get("filed", 0) >= e.get("expected", 0)
    has_sub, has_granular = submission is not None, shadow.get("n_rows", 0) > 0
    projected = bool(projection.get("complete"))
    seen = _lens_seen(session, regulator_org_id, e["org_id"]) if (has_sub and has_granular) else None
    steps = [
        {"key": "submitted", "label": STEP_LABEL["submitted"], "done": filed_all, "partial": (e.get("filed", 0) > 0) and not filed_all,
         "detail": f"{e.get('filed', 0)} of {e.get('expected', 0)} expected filings on record"},
        {"key": "ingested", "label": STEP_LABEL["ingested"], "done": has_sub and has_granular, "partial": has_sub != has_granular,
         "detail": ("template and granular data on file" if has_sub and has_granular else
                    "template on file — granular data missing" if has_sub else
                    "granular data on file — submitted template missing" if has_granular else "nothing ingested yet")},
        {"key": "rebuilt", "label": STEP_LABEL["rebuilt"], "done": has_granular and projected, "partial": has_granular and not projected,
         "detail": (f"{shadow.get('n_located', 0)} of {shadow.get('n_rows', 0)} rows located · projections "
                    f"{projection.get('cells_complete', 0)}/{projection.get('cells', 0)} complete") if has_granular else "no shadow book"},
        {"key": "reviewed", "label": STEP_LABEL["reviewed"], "done": seen is not None, "partial": False,
         "detail": (f"lens run {seen.date().isoformat()} · {n_flagged} questions" if seen is not None else
                    ("lens ready to run" if has_sub and has_granular else "needs step 2 first"))},
        {"key": "engaged", "label": STEP_LABEL["engaged"], "done": eng["n"] > 0 and eng["n_open"] == 0, "partial": eng["n_open"] > 0,
         "detail": (f"{eng['n_open']} open of {eng['n']} raised" + (f" · {eng['n_overdue']} overdue" if eng["n_overdue"] else "")
                    if eng["n"] else "nothing raised yet")},
    ]
    if not in_profile:
        stage, nxt = "out_of_profile", {"label": "Outside your profile — switch profile in Settings to supervise this sector", "to": "/admin"}
    elif not (has_sub and has_granular):
        stage, nxt = ("submitted" if filed_all or e.get("filed", 0) else "collect"), {"label": "Ingest the submitted template and granular data", "to": f"/supervised/{e['org_id']}/intake"}
    elif not projected:
        stage, nxt = "ingested", {"label": "Run scenario projections", "to": f"/supervised/{e['org_id']}/intake"}
    elif seen is None:
        stage, nxt = "rebuilt", {"label": "Review the independent lens", "to": f"/supervised/{e['org_id']}/lens"}
    elif eng["n_open"] > 0:
        stage, nxt = "engaged", {"label": f"Follow up: {eng['n_open']} open" + (f", {eng['n_overdue']} overdue" if eng["n_overdue"] else ""),
                                 "to": f"/supervisor/requests?entity={e['org_id']}"}
    elif eng["n"] > 0:
        stage, nxt = "engaged", {"label": "All requests closed — monitor", "to": f"/supervisor/requests?entity={e['org_id']}"}
    else:
        stage, nxt = "reviewed", {"label": ("Raise the flagged questions with the entity" if (n_flagged or 0) else "No open questions — monitor"),
                                  "to": f"/supervised/{e['org_id']}/lens"}
    return {"steps": steps, "stage": stage, "next": nxt, "site_access": site_access,
            "high_risk_share_pct": (headline or {}).get("value"), "high_risk_flag": (headline or {}).get("flag"),
            "lens_gap_pct": lens_gap_pct, "n_questions": n_flagged, "engagement": eng}
