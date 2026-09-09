"""Engagement: information requests, site-access requests and findings from a supervisor to a supervised entity.

Two-sided by design. The supervisor raises and closes; the entity responds and reports remediation; every step is
a message on one thread both sides read, and both organisations' audit logs record it. Kinds, status flows and who
may set which status come from supervision_profiles.json (engagement) — nothing here hard-codes a flow.
When a request is raised the entity gets a task on its own board, an e-mail to its administrators and a webhook
event; when it closes, the task closes with it.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text

from services.supervision.profiles import registry

SUPERVISOR, ENTITY = "supervisor", "entity"


def config() -> dict:
    return registry()["engagement"]


def kinds() -> dict:
    return config()["kinds"]


def status_label(status: str) -> str:
    return config()["status_labels"].get(status, status.replace("_", " ").capitalize())


def allowed_next(kind: str, side: str) -> list[str]:
    k = kinds().get(kind) or {}
    return list(k.get("entity_sets" if side == ENTITY else "supervisor_sets", []))


def transition_allowed(kind: str, current: str, to: str, side: str) -> bool:
    return to != current and to in allowed_next(kind, side) and to in (kinds().get(kind) or {}).get("statuses", [])


def _criticality(kind: str, severity: Optional[str]) -> str:
    c = config()["task_criticality"].get(kind, "normal")
    return c.get(severity or "", "normal") if isinstance(c, dict) else c


def _row(session, request_id: str) -> Optional[dict]:
    r = session.execute(text("""
        SELECT q.request_id::text AS request_id, q.regulator_org_id::text AS regulator_org_id, q.supervised_org_id::text AS supervised_org_id,
               q.kind, q.title, q.body, q.status, q.severity, q.due_date, q.source, q.raised_at, q.updated_at, q.closed_at,
               q.entity_task_id::text AS entity_task_id, ro.name AS regulator, so.name AS entity, u.full_name AS raised_by,
               q.reference, q.legal_basis, q.response_days, q.signatory, q.letter_sha256, q.issued_at, q.receipt_at, ru.full_name AS receipt_by
        FROM supervision_request q JOIN organizations ro ON ro.org_id = q.regulator_org_id
        JOIN organizations so ON so.org_id = q.supervised_org_id LEFT JOIN users u ON u.user_id = q.raised_by LEFT JOIN users ru ON ru.user_id = q.receipt_by
        WHERE q.request_id = CAST(:i AS uuid)
    """), {"i": request_id}).mappings().first()
    return _fmt(r) if r else None


def _fmt(r) -> dict:
    d = dict(r)
    for k in ("raised_at", "updated_at", "closed_at", "issued_at", "receipt_at"):
        d[k] = d[k].isoformat() if d.get(k) else None
    d["legal_basis"] = d.get("legal_basis") if isinstance(d.get("legal_basis"), dict) else (json.loads(d["legal_basis"]) if d.get("legal_basis") else None)
    d["has_letter"] = bool(d.get("letter_sha256"))
    d["due_date"] = d["due_date"].isoformat() if d.get("due_date") else None
    d["source"] = d["source"] if isinstance(d.get("source"), dict) else (json.loads(d["source"]) if d.get("source") else None)
    d["kind_label"] = (kinds().get(d["kind"]) or {}).get("label", d["kind"])
    d["automatic"] = d.get("raised_by") is None
    d["raised_by"] = d.get("raised_by") or "Automatic — on the authority's published deadline"
    d["status_label"] = status_label(d["status"])
    d["overdue"] = bool(d["due_date"] and d["status"] != (kinds().get(d["kind"]) or {}).get("closed") and date.fromisoformat(d["due_date"]) < date.today())
    return d


def messages(session, request_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT m.message_id::text AS message_id, m.side, m.body, m.status_to, m.created_at, u.full_name AS author
        FROM supervision_request_message m LEFT JOIN users u ON u.user_id = m.author_id
        WHERE m.request_id = CAST(:i AS uuid) ORDER BY m.created_at
    """), {"i": request_id}).mappings().all()
    return [dict(r) | {"created_at": r["created_at"].isoformat(), "status_label": status_label(r["status_to"]) if r["status_to"] else None} for r in rows]


def list_requests(session, *, regulator_org_id: Optional[str] = None, supervised_org_ids: Optional[list[str]] = None,
                  supervised_org_id: Optional[str] = None, status: Optional[str] = None, kind: Optional[str] = None) -> list[dict]:
    where, params = [], {}
    if regulator_org_id:
        where.append("q.regulator_org_id = CAST(:r AS uuid)"); params["r"] = regulator_org_id
    if supervised_org_ids is not None:
        where.append("q.supervised_org_id = ANY(CAST(:ids AS uuid[]))"); params["ids"] = list(supervised_org_ids)
    if supervised_org_id:
        where.append("q.supervised_org_id = CAST(:s AS uuid)"); params["s"] = supervised_org_id
    if status:
        where.append("q.status = :st"); params["st"] = status
    if kind:
        where.append("q.kind = :k"); params["k"] = kind
    rows = session.execute(text(f"""
        SELECT q.request_id::text AS request_id, q.regulator_org_id::text AS regulator_org_id, q.supervised_org_id::text AS supervised_org_id,
               q.kind, q.title, q.body, q.status, q.severity, q.due_date, q.source, q.raised_at, q.updated_at, q.closed_at,
               q.entity_task_id::text AS entity_task_id, ro.name AS regulator, so.name AS entity, u.full_name AS raised_by,
               q.reference, q.legal_basis, q.response_days, q.signatory, q.letter_sha256, q.issued_at, q.receipt_at, ru.full_name AS receipt_by,
               (SELECT count(*) FROM supervision_request_message m WHERE m.request_id = q.request_id) AS n_messages
        FROM supervision_request q JOIN organizations ro ON ro.org_id = q.regulator_org_id
        JOIN organizations so ON so.org_id = q.supervised_org_id LEFT JOIN users u ON u.user_id = q.raised_by LEFT JOIN users ru ON ru.user_id = q.receipt_by
        {'WHERE ' + ' AND '.join(where) if where else ''}
        ORDER BY (q.status = 'closed'), q.due_date NULLS LAST, q.raised_at DESC
    """), params).mappings().all()
    return [_fmt(r) for r in rows]


def get(session, request_id: str, *, regulator_org_id: Optional[str] = None, supervised_org_id: Optional[str] = None) -> Optional[dict]:
    r = _row(session, request_id)
    if not r:
        return None
    if regulator_org_id and r["regulator_org_id"] != regulator_org_id:
        return None
    if supervised_org_id and r["supervised_org_id"] != supervised_org_id:
        return None
    r["messages"] = messages(session, request_id)
    return r


def _notify_entity(session, req: dict, actor_user_id: str) -> None:
    """Task on the entity's board + e-mail to its administrators + webhook event. Never raises."""
    from services.integrations.webhooks import emit_event
    from services.notifications.mailer import queue_email
    try:
        tid = session.execute(text("""
            INSERT INTO regulatory_task (org_id, title, description, status, criticality, source, source_ref, due_date)
            VALUES (CAST(:o AS uuid), :t, :d, 'todo', :c, 'supervisor', :ref, CAST(:due AS date)) RETURNING task_id::text
        """), {"o": req["supervised_org_id"], "t": f"{req['kind_label']} from {req['regulator']}: {req['title']}",
               "d": (req.get("body") or "") + "\n\nRespond under Settings → Entities → Requests from your supervisor.",
               "c": _criticality(req["kind"], req.get("severity")), "ref": req["request_id"], "due": req.get("due_date")}).scalar()
        session.execute(text("UPDATE supervision_request SET entity_task_id = CAST(:t AS uuid) WHERE request_id = CAST(:i AS uuid)"),
                        {"t": tid, "i": req["request_id"]})
        admins = session.execute(text("""
            SELECT DISTINCT u.email FROM users u JOIN user_roles ur ON ur.user_id = u.user_id
            JOIN role_permissions rp ON rp.role_id = ur.role_id JOIN permissions p ON p.permission_id = rp.permission_id
            WHERE u.org_id = CAST(:o AS uuid) AND u.status = 'active' AND p.code = 'admin.users.manage'
        """), {"o": req["supervised_org_id"]}).scalars().all()
        subject = f"{req['regulator']}: {req['kind_label'].lower()} — {req['title']}"
        body = (f"{req['regulator']} has raised a {req['kind_label'].lower()} with your organisation.\n\n{req['title']}\n\n"
                f"{req.get('body') or ''}\n\nDue: {req.get('due_date') or 'not set'}. Respond in Tellumen under Settings → Entities.")
        for em in admins:
            queue_email(session, org_id=req["supervised_org_id"], to_email=em, subject=subject, html=None, text_body=body,
                        kind="supervisor_request", ref_type="supervision_request", ref_id=req["request_id"])
        emit_event(session, req["supervised_org_id"], "supervisor.request.raised",
                   {"request_id": req["request_id"], "kind": req["kind"], "title": req["title"], "due_date": req.get("due_date"),
                    "regulator": req["regulator"]})
    except Exception:  # notification must never block the request itself
        pass


def create(session, *, regulator_org_id: str, supervised_org_id: str, kind: str, title: str, body: Optional[str],
           raised_by: Optional[str], severity: Optional[str] = None, due_date: Optional[str] = None, source: Optional[dict] = None) -> dict:
    """raised_by None = raised automatically by the platform on the authority's published deadline (shown as such)."""
    k = kinds().get(kind)
    if not k:
        raise ValueError(f"unknown request kind {kind!r}")
    if k["severities"] and severity not in k["severities"]:
        raise ValueError(f"{k['label']} needs a severity: {', '.join(k['severities'])}")
    due = due_date or (date.today() + timedelta(days=int(k["default_due_days"]))).isoformat()
    rid = session.execute(text("""
        INSERT INTO supervision_request (regulator_org_id, supervised_org_id, kind, title, body, status, severity, due_date, source, raised_by)
        VALUES (CAST(:r AS uuid), CAST(:s AS uuid), :k, :t, :b, :st, :sev, CAST(:due AS date), CAST(:src AS jsonb), CAST(:u AS uuid))
        RETURNING request_id::text
    """), {"r": regulator_org_id, "s": supervised_org_id, "k": kind, "t": title.strip()[:200], "b": body, "st": k["statuses"][0],
           "sev": severity if k["severities"] else None, "due": due, "src": json.dumps(source) if source else None, "u": raised_by}).scalar()
    session.execute(text("""INSERT INTO supervision_request_message (request_id, side, author_id, body, status_to)
                            VALUES (CAST(:i AS uuid), 'supervisor', CAST(:u AS uuid), :b, :st)"""),
                    {"i": rid, "u": raised_by, "b": body, "st": k["statuses"][0]})
    from services.supervision.correspondence import issue
    issue(session, rid, regulator_org_id=regulator_org_id, supervised_org_id=supervised_org_id, kind=kind, title=title.strip()[:200], body=body,
          severity=severity if k["severities"] else None, due_date=due, source=source, raised_by=raised_by, response_days=int(k["default_due_days"]))
    req = _row(session, rid)
    _notify_entity(session, req, raised_by)
    return _row(session, rid)


def add_message(session, request_id: str, *, side: str, author_id: str, body: Optional[str], status_to: Optional[str] = None) -> dict:
    req = _row(session, request_id)
    if not req:
        raise KeyError(request_id)
    if status_to:
        if not transition_allowed(req["kind"], req["status"], status_to, side):
            raise PermissionError(f"{side} may not move a {req['kind_label'].lower()} from {status_label(req['status'])} to {status_label(status_to)}")
        closed = (kinds()[req["kind"]]["closed"] == status_to)
        session.execute(text("""UPDATE supervision_request SET status = :st, updated_at = now(),
                                closed_at = CASE WHEN :closed THEN now() ELSE NULL END,
                                closed_by = CASE WHEN :closed THEN CAST(:u AS uuid) ELSE NULL END
                                WHERE request_id = CAST(:i AS uuid)"""), {"st": status_to, "closed": closed, "u": author_id, "i": request_id})
        if req.get("entity_task_id"):
            session.execute(text("UPDATE regulatory_task SET status = :s, updated_at = now() WHERE task_id = CAST(:t AS uuid)"),
                            {"s": "done" if closed else ("review" if side == ENTITY else "todo"), "t": req["entity_task_id"]})
    else:
        session.execute(text("UPDATE supervision_request SET updated_at = now() WHERE request_id = CAST(:i AS uuid)"), {"i": request_id})
    session.execute(text("""INSERT INTO supervision_request_message (request_id, side, author_id, body, status_to)
                            VALUES (CAST(:i AS uuid), :side, CAST(:u AS uuid), :b, :st)"""),
                    {"i": request_id, "side": side, "u": author_id, "b": (body or "").strip() or None, "st": status_to})
    return get(session, request_id)


def entity_summary(session, regulator_org_id: str, supervised_org_id: str) -> dict:
    """For the workflow: how far engagement has gone with one entity."""
    r = session.execute(text("""
        SELECT count(*) AS n, count(*) FILTER (WHERE status <> 'closed') AS n_open,
               count(*) FILTER (WHERE status <> 'closed' AND due_date < current_date) AS n_overdue,
               count(*) FILTER (WHERE kind = 'finding' AND status <> 'closed') AS n_findings_open, max(updated_at) AS last
        FROM supervision_request WHERE regulator_org_id = CAST(:r AS uuid) AND supervised_org_id = CAST(:s AS uuid)
    """), {"r": regulator_org_id, "s": supervised_org_id}).mappings().first()
    return {"n": r["n"], "n_open": r["n_open"], "n_overdue": r["n_overdue"], "n_findings_open": r["n_findings_open"],
            "last": r["last"].isoformat() if r["last"] else None}
