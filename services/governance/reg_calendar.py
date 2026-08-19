"""Regulatory calendar — filing deadlines and task due-dates on one timeline.

Combines the statutory filing obligations (what's due, by when) with the team's task due-dates into a single
dated event feed, so a compliance officer sees the whole runway at a glance and what's upcoming next.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.filings import list_obligations


def calendar(session: Session, org_id: str, org_type: str) -> dict:
    today = session.execute(text("SELECT CURRENT_DATE")).scalar()
    events: list[dict] = []

    for o in list_obligations(session, org_id, org_type):
        if not o.get("due_date"):
            continue
        events.append({
            "date": o["due_date"], "kind": "obligation", "title": o["label"],
            "sub": f'{o["period_label"]} · {o["frequency"]}', "ref_id": o.get("filing_id"),
            "status": o["filing_status"], "overdue": bool(o.get("overdue")), "criticality": None,
        })

    rows = session.execute(text("""
        SELECT t.task_id::text AS task_id, t.title, t.status, t.criticality, t.due_date,
               a.full_name AS assignee
        FROM regulatory_task t LEFT JOIN users a ON a.user_id = t.assignee_user_id
        WHERE t.org_id = :o AND t.due_date IS NOT NULL AND t.status NOT IN ('done','cancelled')
        ORDER BY t.due_date
    """), {"o": org_id}).mappings().all()
    for r in rows:
        events.append({
            "date": r["due_date"].isoformat(), "kind": "task", "title": r["title"],
            "sub": (r["assignee"] or "unassigned"), "ref_id": r["task_id"],
            "status": r["status"], "overdue": r["due_date"] < today, "criticality": r["criticality"],
        })

    events.sort(key=lambda e: e["date"])
    upcoming = [e for e in events if e["date"] >= today.isoformat()][:12]
    return {"events": events, "upcoming": upcoming, "today": today.isoformat()}
