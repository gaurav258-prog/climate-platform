"""Supervisor-set deadlines and the automatic follow-up on missing items.

A supervisory body generates its calendar for a period from the mandate registry (the act's due rule), adapts a
date where its own practice differs, and publishes. Publishing writes the date onto every applicable entity's own
obligations calendar (regulatory_obligation, source 'supervisor') — one date both sides see — and tells the entity.
A daily sweep then raises an information request for every applicable entity that has not released the filing:
a reminder before the due date and an overdue notice after it, each exactly once, on the request thread both sides
read. Reminder windows come from the registry; nothing here names a sector.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text

from services.supervision.mandates import (
    APPLIES,
    due_date,
    effective,
    entity_attributes,
    evaluate,
    mandate,
    mandates_for,
    registry,
    settings,
)

FILED = ("submitted", "accepted", "approved", "attested", "released")
DEFAULT_REMINDERS = {"before_due_days": 14, "after_due_days": 1}


def reminders() -> dict:
    return {**DEFAULT_REMINDERS, **(registry().get("reminders") or {})}


def stage_for(due: date, today: date, r: Optional[dict] = None) -> Optional[str]:
    """Which follow-up a published deadline calls for today: 'overdue' after due + after_due_days, 'reminder' from
    due − before_due_days, else None. Pure."""
    r = r or reminders()
    if today >= due + timedelta(days=int(r["after_due_days"])):
        return "overdue"
    if today >= due - timedelta(days=int(r["before_due_days"])):
        return "reminder"
    return None


def _period_end(period_label: str) -> date:
    y = int("".join(ch for ch in period_label if ch.isdigit())[-4:])
    return date(y, 12, 31)


# ── the supervisory calendar ────────────────────────────────────────────────────────────────────────────────
def generate(session, reg_org_id: str, cfg: dict, period_label: str) -> list[dict]:
    """Draft a deadline for every calendar mandate in the profile (per-event mandates such as EUDR have no date)."""
    pe = _period_end(period_label)
    st = settings(session, reg_org_id)
    made = []
    for m in mandates_for(list(cfg["sectors"].keys())):
        e = effective(m, st.get(m["id"]))
        fw = e["deliverable"].get("framework")
        if not e["enabled"] or not fw:
            continue
        d = due_date(e, pe)
        if d is None:
            continue
        row = session.execute(text("""
            INSERT INTO supervision_deadline (regulator_org_id, mandate_id, framework, period_label, period_end, due_date, due_source)
            VALUES (CAST(:r AS uuid), :m, :fw, :pl, :pe, :d, 'registry')
            ON CONFLICT (regulator_org_id, mandate_id, period_label) DO NOTHING RETURNING deadline_id::text
        """), {"r": reg_org_id, "m": m["id"], "fw": fw, "pl": period_label, "pe": pe, "d": d}).scalar()
        if row:
            made.append(row)
    return made


def list_deadlines(session, reg_org_id: str, period_label: Optional[str] = None) -> list[dict]:
    rows = session.execute(text(f"""
        SELECT d.deadline_id::text AS deadline_id, d.mandate_id, d.framework, d.period_label, d.period_end, d.due_date, d.due_source, d.note, d.status,
               d.published_at, u.full_name AS published_by,
               (SELECT count(*) FROM supervision_deadline_notice n WHERE n.deadline_id = d.deadline_id AND n.stage = 'reminder') AS n_reminders,
               (SELECT count(*) FROM supervision_deadline_notice n WHERE n.deadline_id = d.deadline_id AND n.stage = 'overdue') AS n_overdue
        FROM supervision_deadline d LEFT JOIN users u ON u.user_id = d.published_by
        WHERE d.regulator_org_id = CAST(:r AS uuid) {'AND d.period_label = :pl' if period_label else ''}
        ORDER BY d.period_label DESC, d.due_date
    """), {"r": reg_org_id, "pl": period_label}).mappings().all()
    out = []
    for r in rows:
        m = mandate(r["mandate_id"]) or {}
        out.append(dict(r) | {"period_end": r["period_end"].isoformat(), "due_date": r["due_date"].isoformat(),
                              "published_at": r["published_at"].isoformat() if r["published_at"] else None,
                              "short": m.get("short", r["mandate_id"]), "title": m.get("title"), "registry_rule": (m.get("deliverable") or {}).get("due", {}).get("label"),
                              "registry_due": (due_date(m, r["period_end"]).isoformat() if m else None)})
    return out


def set_due(session, reg_org_id: str, deadline_id: str, due: Optional[date], note: Optional[str], by_user_id: str) -> Optional[dict]:
    row = session.execute(text("SELECT mandate_id, period_end, status FROM supervision_deadline WHERE deadline_id = CAST(:d AS uuid) AND regulator_org_id = CAST(:r AS uuid)"),
                          {"d": deadline_id, "r": reg_org_id}).mappings().first()
    if not row:
        return None
    if due is None:   # back to the act's rule
        due, src = due_date(mandate(row["mandate_id"]), row["period_end"]), "registry"
    else:
        src = "set"
    session.execute(text("""UPDATE supervision_deadline SET due_date = :d, due_source = :s, note = COALESCE(:n, note), updated_at = now()
                            WHERE deadline_id = CAST(:id AS uuid)"""), {"d": due, "s": src, "n": note, "id": deadline_id})
    if row["status"] == "published":
        _propagate(session, reg_org_id, deadline_id, by_user_id)
    return {"deadline_id": deadline_id, "due_date": due.isoformat(), "due_source": src}


def applicable_entities(session, reg_org_id: str, cfg: dict, mandate_id: str) -> list[dict]:
    """Entities in the body's population for which this mandate applies (cannot-determine and not-applicable are listed with their status)."""
    st = settings(session, reg_org_id)
    m = effective(mandate(mandate_id), st.get(mandate_id))
    ents = session.execute(text("""SELECT o.org_id::text AS org_id, o.name, o.type FROM supervision_scope ss JOIN organizations o ON o.org_id = ss.supervised_org_id
                                   WHERE ss.regulator_org_id = CAST(:r AS uuid) AND ss.active"""), {"r": reg_org_id}).mappings().all()
    out = []
    for e in ents:
        if e["type"] not in m["sectors"] or e["type"] not in cfg["sectors"]:
            continue
        ev = evaluate(m, entity_attributes(session, e["org_id"]))
        out.append({"org_id": e["org_id"], "name": e["name"], "type": e["type"], "status": ev["status"], "missing": ev["missing"]})
    return out


def _propagate(session, reg_org_id: str, deadline_id: str, by_user_id: str, cfg: Optional[dict] = None) -> dict:
    """Write the published date onto every applicable entity's obligations calendar and tell the entity."""
    from services.integrations.webhooks import emit_event
    from services.notifications.mailer import queue_email
    from services.supervision.profiles import resolve
    d = session.execute(text("""SELECT mandate_id, framework, period_label, period_end, due_date, note FROM supervision_deadline
                                WHERE deadline_id = CAST(:d AS uuid) AND regulator_org_id = CAST(:r AS uuid)"""), {"d": deadline_id, "r": reg_org_id}).mappings().first()
    reg_name = session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": reg_org_id}).scalar()
    cfg = cfg or resolve(None, _overrides(session, reg_org_id))
    n_set, n_skipped = 0, 0
    for e in applicable_entities(session, reg_org_id, cfg, d["mandate_id"]):
        if e["status"] != APPLIES:
            n_skipped += 1
            continue
        existing = session.execute(text("""SELECT obligation_id, due_date FROM regulatory_obligation WHERE org_id = CAST(:o AS uuid) AND framework = :fw
                                           AND period_end = :pe AND entity_id IS NULL"""), {"o": e["org_id"], "fw": d["framework"], "pe": d["period_end"]}).mappings().first()
        if existing:
            session.execute(text("""UPDATE regulatory_obligation SET due_date = :due, source = 'supervisor', supervision_deadline_id = CAST(:d AS uuid), set_by = :by,
                                    note = :n WHERE obligation_id = :id"""), {"due": d["due_date"], "d": deadline_id, "by": reg_name, "n": d["note"], "id": existing["obligation_id"]})
        else:
            session.execute(text("""INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency, note, source, supervision_deadline_id, set_by)
                                    VALUES (CAST(:o AS uuid), :fw, :pe, :pl, :due, 'annual', :n, 'supervisor', CAST(:d AS uuid), :by)"""),
                            {"o": e["org_id"], "fw": d["framework"], "pe": d["period_end"], "pl": d["period_label"], "due": d["due_date"], "n": d["note"], "d": deadline_id, "by": reg_name})
        n_set += 1
        try:
            m = mandate(d["mandate_id"]) or {}
            admins = session.execute(text("""SELECT DISTINCT u.email FROM users u JOIN user_roles ur ON ur.user_id = u.user_id JOIN role_permissions rp ON rp.role_id = ur.role_id
                                             JOIN permissions p ON p.permission_id = rp.permission_id WHERE u.org_id = CAST(:o AS uuid) AND u.status = 'active' AND p.code = 'admin.users.manage'"""),
                                     {"o": e["org_id"]}).scalars().all()
            for em in admins:
                queue_email(session, org_id=e["org_id"], to_email=em, subject=f"{reg_name}: filing deadline {d['period_label']} — {m.get('short', d['framework'])}: {d['due_date'].isoformat()}",
                            html=None, text_body=f"{reg_name} has set the deadline for {m.get('title', d['framework'])} ({d['period_label']}) to {d['due_date'].isoformat()}. "
                                                 f"{d['note'] or ''} It now appears in your obligations calendar in Tellumen.", kind="supervision_deadline", ref_type="supervision_deadline", ref_id=deadline_id)
            emit_event(session, e["org_id"], "supervision.deadline.published", {"deadline_id": deadline_id, "framework": d["framework"], "period_label": d["period_label"], "due_date": d["due_date"].isoformat(), "regulator": reg_name})
        except Exception:
            pass
    return {"entities_set": n_set, "entities_skipped": n_skipped}


def _overrides(session, reg_org_id: str) -> dict:
    row = session.execute(text("SELECT profile, default_scenario, default_horizon, thresholds FROM supervisor_settings WHERE org_id = CAST(:o AS uuid)"), {"o": reg_org_id}).mappings().first()
    return dict(row) if row else {}


def publish(session, reg_org_id: str, deadline_id: str, by_user_id: str, cfg: dict) -> Optional[dict]:
    ok = session.execute(text("""UPDATE supervision_deadline SET status = 'published', published_at = now(), published_by = CAST(:u AS uuid), updated_at = now()
                                 WHERE deadline_id = CAST(:d AS uuid) AND regulator_org_id = CAST(:r AS uuid) RETURNING deadline_id"""),
                         {"u": by_user_id, "d": deadline_id, "r": reg_org_id}).scalar()
    if not ok:
        return None
    return _propagate(session, reg_org_id, deadline_id, by_user_id, cfg)


# ── the sweep: missing items become requests, once ────────────────────────────────────────────────────────
def _filed(session, org_id: str, framework: str, period_label: str) -> bool:
    return session.execute(text("""SELECT 1 FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) AND framework = :fw AND period_label = :pl
                                   AND status = ANY(CAST(:filed AS text[]))"""), {"o": org_id, "fw": framework, "pl": period_label, "filed": list(FILED)}).first() is not None


def sweep(session, reg_org_id: Optional[str] = None, today: Optional[date] = None) -> dict:
    """For every published deadline of every (or one) supervisory body: reminder before due, overdue notice after —
    each once per entity, as an information request on the thread. Returns what it raised."""
    from services.supervision.engagement import create
    from services.supervision.profiles import resolve
    today = today or date.today()
    r = reminders()
    regs = session.execute(text(f"SELECT DISTINCT regulator_org_id::text FROM supervision_deadline WHERE status = 'published' {'AND regulator_org_id = CAST(:r AS uuid)' if reg_org_id else ''}"),
                           {"r": reg_org_id}).scalars().all()
    raised = []
    for reg in regs:
        cfg = resolve(None, _overrides(session, reg))
        reg_name = session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": reg}).scalar()
        for d in list_deadlines(session, reg):
            if d["status"] != "published":
                continue
            due = date.fromisoformat(d["due_date"])
            stage = stage_for(due, today, r)
            if stage is None:
                continue
            for e in applicable_entities(session, reg, cfg, d["mandate_id"]):
                if e["status"] != APPLIES or _filed(session, e["org_id"], d["framework"], d["period_label"]):
                    continue
                already = session.execute(text("SELECT 1 FROM supervision_deadline_notice WHERE deadline_id = CAST(:d AS uuid) AND supervised_org_id = CAST(:o AS uuid) AND stage = :s"),
                                          {"d": d["deadline_id"], "o": e["org_id"], "s": stage}).first()
                if already:
                    continue
                days = (due - today).days
                title = (f"{d['short']} {d['period_label']}: due {d['due_date']} — not yet received" if stage == "reminder"
                         else f"{d['short']} {d['period_label']}: overdue since {d['due_date']}")
                body = (f"{reg_name} has not received your {d['title']} for {d['period_label']}. The deadline is {d['due_date']} ({days} days). "
                        f"Please release it through your filing workspace, or tell us on this thread if it will be late."
                        if stage == "reminder" else
                        f"The deadline for your {d['title']} ({d['period_label']}) was {d['due_date']} and {reg_name} has not received it. "
                        f"Please release it without delay, or tell us on this thread when it will arrive and why.")
                req = create(session, regulator_org_id=reg, supervised_org_id=e["org_id"], kind="information_request", title=title, body=body,
                             raised_by=None, due_date=(due if stage == "reminder" else (today + timedelta(days=10))).isoformat(),
                             source={"type": "deadline", "stage": stage, "mandate_id": d["mandate_id"], "framework": d["framework"], "period_label": d["period_label"], "deadline_id": d["deadline_id"]})
                session.execute(text("INSERT INTO supervision_deadline_notice (deadline_id, supervised_org_id, stage, request_id) VALUES (CAST(:d AS uuid), CAST(:o AS uuid), :s, CAST(:q AS uuid))"),
                                {"d": d["deadline_id"], "o": e["org_id"], "s": stage, "q": req["request_id"]})
                for audited in (reg, e["org_id"]):
                    session.execute(text("""INSERT INTO access_audit_log (org_id, actor_user_id, action, target_type, target_id, detail)
                                            VALUES (CAST(:o AS uuid), NULL, 'supervisor.request.raised', 'supervision_request', :t, CAST(:dt AS jsonb))"""),
                                    {"o": audited, "t": req["request_id"], "dt": __import__("json").dumps({"kind": "information_request", "title": title, "regulator_org_id": reg,
                                                                                                             "supervised_org_id": e["org_id"], "automatic": True, "stage": stage})})
                raised.append({"regulator": reg_name, "entity": e["name"], "stage": stage, "deadline": d["short"], "period": d["period_label"], "request_id": req["request_id"]})
        session.commit()
    return {"as_of": today.isoformat(), "raised": raised, "n": len(raised)}


def status_view(session, reg_org_id: str, cfg: dict, period_label: str) -> dict:
    """Per deadline: how many applicable entities, filed, outstanding, reminded, overdue-notified."""
    out = []
    for d in list_deadlines(session, reg_org_id, period_label):
        ents = applicable_entities(session, reg_org_id, cfg, d["mandate_id"])
        app = [e for e in ents if e["status"] == APPLIES]
        filed = [e for e in app if _filed(session, e["org_id"], d["framework"], d["period_label"])]
        notices = session.execute(text("SELECT supervised_org_id::text AS org_id, stage FROM supervision_deadline_notice WHERE deadline_id = CAST(:d AS uuid)"), {"d": d["deadline_id"]}).mappings().all()
        rem = {n["org_id"] for n in notices if n["stage"] == "reminder"}; ovd = {n["org_id"] for n in notices if n["stage"] == "overdue"}
        out.append({**d, "n_applicable": len(app), "n_cannot": sum(1 for e in ents if e["status"] != APPLIES and e["missing"]), "n_filed": len(filed),
                    "outstanding": [{"org_id": e["org_id"], "name": e["name"], "reminded": e["org_id"] in rem, "overdue_notified": e["org_id"] in ovd}
                                    for e in app if e["org_id"] not in {f["org_id"] for f in filed}]})
    return {"period_label": period_label, "deadlines": out, "reminders": reminders(),
            "note": "Publishing writes the date onto each applicable entity's own obligations calendar and tells the entity. The daily sweep raises "
                    "an information request for every applicable entity that has not released the filing — a reminder before the due date, an overdue "
                    "notice after it — each once. Entities whose applicability cannot be determined are not chased until their attributes are known."}


def sweep_all() -> dict:
    """Worker entry point: every supervisory body's published deadlines."""
    from core.db.session import get_session
    with get_session() as s:
        return sweep(s)


def apply_published(session, reg_org_id: str, by_user_id: Optional[str], cfg: Optional[dict] = None) -> int:
    """Re-propagate every published deadline of this authority — used when an entity joins the population later,
    so it receives the dates already published. Idempotent upserts."""
    ids = session.execute(text("SELECT deadline_id::text FROM supervision_deadline WHERE regulator_org_id = CAST(:r AS uuid) AND status = 'published'"),
                          {"r": reg_org_id}).scalars().all()
    for d in ids:
        _propagate(session, reg_org_id, d, by_user_id or "", cfg)
    return len(ids)
