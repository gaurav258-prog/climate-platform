"""Regulatory-notification clock — the 'notify the regulator within N hours' workflow the calendar can't hold.

A human flags a breach or incident as notifiable; raise() stamps when it arose, the window, and therefore when
it is DUE. open_events() reports each one's live countdown and whether it is overdue. record() captures the
evidence of what was actually sent (reference, recipient, time). Emits notification.* webhooks so a customer's
systems can react. Which events are notifiable is a jurisdiction-specific compliance judgement — raising one is
an explicit act; the platform owns the clock, the overdue detection and the audit record.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_WINDOW_HOURS = 72   # a sensible default; the caller sets the real statutory window per event


def _emit(session, org_id, event_type, payload):
    try:
        from services.integrations.webhooks import emit_event
        emit_event(session, org_id, event_type, payload)
    except Exception:
        pass


def raise_event(session: Session, org_id: str, *, title: str, source_type: str = "manual",
                source_ref: Optional[str] = None, category: str = "material_breach",
                severity: Optional[str] = None, authority: Optional[str] = None,
                arose_at_iso: Optional[str] = None, window_hours: int = DEFAULT_WINDOW_HOURS,
                assignee_user_id: Optional[str] = None, user_id: Optional[str] = None) -> dict:
    """Open a notifiable event with its clock. De-dupes on (source_type, source_ref) while open."""
    eid = str(uuid.uuid4())
    row = session.execute(text("""
        INSERT INTO notifiable_event
            (event_id, org_id, source_type, source_ref, title, category, severity, authority,
             arose_at, window_hours, due_at, created_by, assignee_user_id)
        VALUES (CAST(:e AS uuid), CAST(:o AS uuid), :st, :sr, :t, :cat, :sev, :auth,
                COALESCE(CAST(:arose AS timestamptz), now()), :w,
                COALESCE(CAST(:arose AS timestamptz), now()) + (:w || ' hours')::interval,
                CAST(:u AS uuid), CAST(:asg AS uuid))
        ON CONFLICT DO NOTHING
        RETURNING event_id::text AS event_id, due_at
    """), {"e": eid, "o": org_id, "st": source_type, "sr": source_ref, "t": title[:240], "cat": category,
           "sev": severity, "auth": authority, "arose": arose_at_iso, "w": window_hours,
           "u": user_id, "asg": assignee_user_id}).mappings().first()
    session.commit()
    if row:
        _emit(session, org_id, "notification.raised", {"event_id": row["event_id"], "title": title,
              "category": category, "authority": authority, "window_hours": window_hours,
              "due_at": row["due_at"].isoformat() if row["due_at"] else None})
        return {"event_id": row["event_id"], "created": True}
    # already an open event for this source
    existing = session.execute(text("""
        SELECT event_id::text AS event_id FROM notifiable_event
        WHERE org_id = CAST(:o AS uuid) AND source_type = :st AND source_ref = :sr AND status = 'open'
    """), {"o": org_id, "st": source_type, "sr": source_ref}).scalar()
    return {"event_id": existing, "created": False}


def record(session: Session, org_id: str, event_id: str, *, notified_ref: Optional[str],
           notified_to: Optional[str], user_id: Optional[str]) -> bool:
    res = session.execute(text("""
        UPDATE notifiable_event
        SET status = 'notified', notified_at = now(), notified_ref = :ref, notified_to = :to, notified_by = CAST(:u AS uuid)
        WHERE org_id = CAST(:o AS uuid) AND event_id = CAST(:e AS uuid) AND status = 'open'
    """), {"o": org_id, "e": event_id, "ref": notified_ref, "to": notified_to, "u": user_id})
    session.commit()
    if res.rowcount:
        _emit(session, org_id, "notification.sent", {"event_id": event_id, "notified_ref": notified_ref})
    return bool(res.rowcount)


def dismiss(session: Session, org_id: str, event_id: str, *, reason: str, user_id: Optional[str]) -> bool:
    res = session.execute(text("""
        UPDATE notifiable_event SET status = 'dismissed', dismiss_reason = :r, notified_by = CAST(:u AS uuid)
        WHERE org_id = CAST(:o AS uuid) AND event_id = CAST(:e AS uuid) AND status = 'open'
    """), {"o": org_id, "e": event_id, "r": reason, "u": user_id})
    session.commit()
    return bool(res.rowcount)


def open_events(session: Session, org_id: str) -> dict:
    rows = session.execute(text("""
        SELECT event_id::text AS event_id, title, category, severity, authority, source_type, source_ref,
               arose_at, due_at, status, notified_at, notified_ref, notified_to,
               EXTRACT(EPOCH FROM (due_at - now())) AS remaining_s,
               (status = 'open' AND now() > due_at) AS overdue
        FROM notifiable_event
        WHERE org_id = CAST(:o AS uuid) AND status IN ('open', 'notified')
        ORDER BY (status = 'open') DESC, due_at ASC
        LIMIT 100
    """), {"o": org_id}).mappings().all()
    events = []
    for r in rows:
        rem_h = round(float(r["remaining_s"]) / 3600, 1) if r["remaining_s"] is not None else None
        events.append({
            "event_id": r["event_id"], "title": r["title"], "category": r["category"], "severity": r["severity"],
            "authority": r["authority"], "source_type": r["source_type"], "source_ref": r["source_ref"],
            "arose_at": r["arose_at"].isoformat(), "due_at": r["due_at"].isoformat(),
            "status": r["status"], "overdue": bool(r["overdue"]), "hours_remaining": rem_h,
            "notified_at": r["notified_at"].isoformat() if r["notified_at"] else None,
            "notified_ref": r["notified_ref"], "notified_to": r["notified_to"],
        })
    summary = {
        "n_open": sum(1 for e in events if e["status"] == "open"),
        "n_overdue": sum(1 for e in events if e["overdue"]),
        "next_due_hours": min([e["hours_remaining"] for e in events if e["status"] == "open"], default=None),
    }
    return {"events": events, "summary": summary}
