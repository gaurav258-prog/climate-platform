"""CRCS · proactive alerts — turn the pull-based outlook into a push service.

Sweeps each org's regulatory outlook and, for anything that warrants attention — a machine-detected change at
the source, or a deadline coming within the alert window — raises a per-org alert ONCE (deduped): it spins a
Kanban task the team owns, emails the filing contact via the outbox, and emits a `regulatory.alert` webhook.
Everything reuses existing plumbing (tasks / mailer / webhooks); nothing here is fabricated — an alert only
fires off a real detected change or a real effective date from the register.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

ALERT_WINDOW_DAYS = 180   # a deadline within ~6 months is worth a "start preparing" alert


def sweep(session: Session, org_id: str, org_type: str | None) -> dict:
    """Raise any new alerts for one org (idempotent — already-alerted changes are skipped)."""
    from services.governance import tasks as T
    from services.governance.reg_outlook import outlook
    from services.integrations.webhooks import emit_event
    from services.notifications.mailer import queue_email

    o = outlook(org_type, session, org_id)
    org = session.execute(text("SELECT name, filing_contact_email FROM organizations WHERE org_id=:o"),
                          {"o": org_id}).mappings().first()
    # notify the filing contact if set, else the org's active admins
    contact = (org or {}).get("filing_contact_email")
    recipients = [contact] if contact else list(session.execute(text("""
        SELECT DISTINCT u.email FROM users u
        JOIN user_roles ur ON ur.user_id = u.user_id JOIN roles r ON r.role_id = ur.role_id
        WHERE u.org_id = :o AND u.status = 'active' AND r.name = 'admin'"""), {"o": org_id}).scalars().all())
    raised = []

    for c in o.get("coming", []):
        dl = (c.get("impact") or {}).get("deadline") or {}
        days = dl.get("days")
        detected = c.get("source") == "detected"
        approaching = isinstance(days, int) and 0 <= days <= ALERT_WINDOW_DAYS
        if not (detected or approaching):
            continue
        kind = "detected" if detected else "deadline"
        akey = f"{kind}:{c.get('framework')}:{c.get('date')}"
        if session.execute(text("SELECT 1 FROM reg_alert WHERE org_id=:o AND alert_key=:k"),
                           {"o": org_id, "k": akey}).first():
            continue   # already alerted

        crit = "high" if (detected or (isinstance(days, int) and days <= 90)) else "normal"
        title = (f"New regulatory change detected — {c['title']}" if detected
                 else f"Regulatory deadline approaching — {c['title']} ({days} days)")
        desc = c.get("whats_changing")
        if c.get("prepare"):
            desc = f"{desc}\n\nTo prepare: {c['prepare']}"

        task_id = None
        try:
            task = T.create_task(session, org_id, None, title=title, description=desc,   # system-raised (no actor)
                                 criticality=crit, source="regulatory_change", source_ref=akey, due_date=c.get("date"))
            task_id = task.get("task_id")
        except Exception:
            session.rollback()   # never let a task failure poison the alert/email/webhook writes

        session.execute(text("""INSERT INTO reg_alert (org_id, alert_key, framework, kind, title, effective_date, task_id)
                                VALUES (:o,:k,:fw,:kind,:t,:d, CAST(:tid AS uuid))
                                ON CONFLICT (org_id, alert_key) DO NOTHING"""),
                        {"o": org_id, "k": akey, "fw": c.get("framework"), "kind": kind, "t": title,
                         "d": c.get("date"), "tid": str(task_id) if task_id else None})

        body = (f"{title}\n\n{desc or ''}\n\n"
                f"Effective: {c.get('when')}\nSource: {c.get('citation')}\n\n"
                f"Open Tellumen → Regulatory outlook to review, or your Tasks board to action it.")
        for to in recipients:
            try:
                queue_email(session, org_id=org_id, to_email=to, subject=f"[Tellumen] {title}",
                            html=None, text_body=body, kind="reg_alert",
                            ref_type="task", ref_id=(str(task_id) if task_id else None))
            except Exception:
                pass
        try:
            emit_event(session, org_id, "regulatory.alert",
                       {"kind": kind, "framework": c.get("framework"), "title": c["title"],
                        "effective_date": c.get("date"), "days": days, "task_id": str(task_id) if task_id else None})
        except Exception:
            pass
        raised.append({"kind": kind, "title": c["title"], "task_id": str(task_id) if task_id else None,
                       "effective_date": c.get("date")})

    session.commit()
    return {"raised": raised, "n": len(raised)}


def sweep_all(session: Session) -> dict:
    """Sweep every active org — for the scheduled job."""
    orgs = session.execute(text("SELECT org_id, type FROM organizations")).mappings().all()
    total = 0
    for r in orgs:
        try:
            total += sweep(session, str(r["org_id"]), r["type"]).get("n", 0)
        except Exception:
            continue
    return {"orgs": len(orgs), "raised": total}


def list_alerts(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT alert_key, framework, kind, title, effective_date, task_id, raised_at
        FROM reg_alert WHERE org_id=:o ORDER BY raised_at DESC LIMIT 50"""), {"o": org_id}).mappings().all()
    return [{"alert_key": r["alert_key"], "framework": r["framework"], "kind": r["kind"], "title": r["title"],
             "effective_date": r["effective_date"].isoformat() if r["effective_date"] else None,
             "task_id": str(r["task_id"]) if r["task_id"] else None,
             "raised_at": r["raised_at"].date().isoformat() if r["raised_at"] else None} for r in rows]
