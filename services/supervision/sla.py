"""Engagement SLA and the obligations calendar per authority.

SLA: computed only from timestamps the request thread already records — sent (issued_at, else raised_at),
acknowledged (receipt_at: the entity's formal receipt), responded (responded_at: the entity's first status step),
closed (closed_at) and the due date. Nothing is estimated; a request without a timestamp is simply not in that
metric's sample, and the sample size is always returned next to the median.

Calendar: for a period, every enabled mandate in the authority's profile → the receiving authority named on its
channel (mandate registry `channels[channel_id].authority`), the due date the supervisory body works to (its own
drafted/published deadline if it has one, else the act's rule as adapted), and the entities to which it applies.
Events carry the same shape as the regulated side's calendar (services.governance.reg_calendar) — one concept.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from statistics import median
from typing import Optional

from sqlalchemy import text

AGEING_BUCKETS = (("1-7", 1, 7), ("8-30", 8, 30), ("31-90", 31, 90), ("90+", 91, None))


# ── pure metric computation ─────────────────────────────────────────────────────────────────────────────────
def _hours(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    return round((b - a).total_seconds() / 3600.0, 2) if a and b and b >= a else None


def _p(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))], 2)


def _stat(values: list[float]) -> dict:
    return {"n": len(values), "median": round(median(values), 2) if values else None, "p90": _p(values, 0.9), "max": round(max(values), 2) if values else None}


def ageing_bucket(days: int) -> Optional[str]:
    for label, lo, hi in AGEING_BUCKETS:
        if days >= lo and (hi is None or days <= hi):
            return label
    return None


def compute(rows: list[dict], today: Optional[date] = None) -> dict:
    """rows: {kind, closed(bool), sent_at, acknowledged_at, responded_at, closed_at (datetimes|None), due_date (date|None)}.
    → time_to_acknowledge / time_to_respond / time_to_close in hours (n, median, p90, max), response timeliness
    against the due date, and the open items' overdue count with ageing buckets."""
    today = today or datetime.now(timezone.utc).date()
    ack = [h for r in rows if (h := _hours(r.get("sent_at"), r.get("acknowledged_at"))) is not None]
    resp = [h for r in rows if (h := _hours(r.get("sent_at"), r.get("responded_at"))) is not None]
    close = [h for r in rows if (h := _hours(r.get("sent_at"), r.get("closed_at"))) is not None]
    with_due = [r for r in rows if r.get("responded_at") and r.get("due_date")]
    on_time = sum(1 for r in with_due if r["responded_at"].date() <= r["due_date"])
    open_rows = [r for r in rows if not r.get("closed")]
    overdue = [r for r in open_rows if r.get("due_date") and r["due_date"] < today]
    buckets = {label: 0 for label, _, _ in AGEING_BUCKETS}
    ages = []
    for r in overdue:
        d = (today - r["due_date"]).days
        ages.append(d)
        b = ageing_bucket(d)
        if b:
            buckets[b] += 1
    awaiting_ack = [r for r in open_rows if not r.get("acknowledged_at")]
    awaiting_resp = [r for r in open_rows if not r.get("responded_at")]
    return {
        "n": len(rows), "n_open": len(open_rows), "n_closed": len(rows) - len(open_rows),
        "time_to_acknowledge_hours": _stat(ack), "time_to_respond_hours": _stat(resp), "time_to_close_hours": _stat(close),
        "responded_on_time": {"n": len(with_due), "on_time": on_time, "rate": round(on_time / len(with_due), 3) if with_due else None},
        "awaiting_acknowledgement": {"n": len(awaiting_ack), "oldest_days": max(((today - r["sent_at"].date()).days for r in awaiting_ack if r.get("sent_at")), default=None)},
        "awaiting_response": {"n": len(awaiting_resp)},
        "overdue": {"n": len(overdue), "ageing": buckets, "oldest_days": max(ages, default=None), "total_days": sum(ages)},
    }


def by_group(rows: list[dict], key: str, today: Optional[date] = None) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(str(r.get(key) or ""), []).append(r)
    out = [{key: k, "label": g[0].get(f"{key}_label", k), **compute(g, today)} for k, g in groups.items()]
    return sorted(out, key=lambda x: (-x["overdue"]["n"], -x["n_open"], x["label"]))


# ── loader: the real thread timestamps ──────────────────────────────────────────────────────────────────────
def load_rows(session, regulator_org_id: str, supervised_org_ids: list[str]) -> list[dict]:
    from services.supervision.engagement import kinds
    ks = kinds()
    rs = session.execute(text("""
        SELECT q.request_id::text AS request_id, q.kind, q.status, q.severity, q.due_date, q.raised_at, q.issued_at, q.receipt_at, q.responded_at, q.closed_at,
               q.supervised_org_id::text AS supervised_org_id, so.name AS entity, ro.name AS regulator
        FROM supervision_request q JOIN organizations so ON so.org_id = q.supervised_org_id JOIN organizations ro ON ro.org_id = q.regulator_org_id
        WHERE q.regulator_org_id = CAST(:r AS uuid) AND q.supervised_org_id = ANY(CAST(:ids AS uuid[]))
    """), {"r": regulator_org_id, "ids": list(supervised_org_ids)}).mappings().all()
    return [{"request_id": r["request_id"], "kind": r["kind"], "kind_label": (ks.get(r["kind"]) or {}).get("label", r["kind"]), "status": r["status"],
             "closed": r["status"] == (ks.get(r["kind"]) or {}).get("closed", "closed"), "sent_at": r["issued_at"] or r["raised_at"],
             "acknowledged_at": r["receipt_at"], "responded_at": r["responded_at"], "closed_at": r["closed_at"], "due_date": r["due_date"],
             "supervised_org_id": r["supervised_org_id"], "supervised_org_id_label": r["entity"], "regulator": r["regulator"]} for r in rs]


def sla_view(session, regulator_org_id: str, supervised_org_ids: list[str], today: Optional[date] = None) -> dict:
    rows = load_rows(session, regulator_org_id, supervised_org_ids)
    name = rows[0]["regulator"] if rows else session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": regulator_org_id}).scalar()
    today = today or date.today()
    return {"as_of": today.isoformat(),
            "authorities": [{"org_id": regulator_org_id, "authority": name, **compute(rows, today),
                             "by_kind": by_group(rows, "kind", today), "by_entity": by_group(rows, "supervised_org_id", today)}],
            "definitions": {"time_to_acknowledge_hours": "receipt_at − issued_at (falls back to raised_at): the entity's formal receipt of the letter",
                            "time_to_respond_hours": "responded_at − issued_at: the entity's first status step on the thread (responded / remediation planned)",
                            "time_to_close_hours": "closed_at − issued_at: the supervisor's closure",
                            "overdue": "open requests whose due date has passed, aged in days since the due date",
                            "ageing_buckets": [b[0] for b in AGEING_BUCKETS]},
            "note": "Every figure is computed from timestamps the thread recorded; a request without a timestamp is outside that sample (n shown)."}


# ── the obligations calendar, per receiving authority ───────────────────────────────────────────────────────
def authority_calendar(session, reg_org_id: str, cfg: dict, period_label: str, today: Optional[date] = None) -> dict:
    from services.supervision.deadlines import (
        _filed,
        _period_end,
        applicable_entities,
        list_deadlines,
    )
    from services.supervision.mandates import (
        APPLIES,
        due_date,
        effective,
        mandates_for,
        registry,
        settings,
    )
    today = today or date.today()
    pe = _period_end(period_label)
    reg = registry()
    st = settings(session, reg_org_id)
    set_by_mandate = {d["mandate_id"]: d for d in list_deadlines(session, reg_org_id, period_label)}
    groups: dict[str, dict] = {}
    undated = []
    for m in mandates_for(list(cfg["sectors"].keys())):
        e = effective(m, st.get(m["id"]))
        if not e["enabled"]:
            continue
        ch = reg["channels"].get(e["deliverable"].get("channel_id")) or {}
        authority = ch.get("authority") or "Authority not named on the channel"
        ents = applicable_entities(session, reg_org_id, cfg, m["id"])
        app = [x for x in ents if x["status"] == APPLIES]
        fw = e["deliverable"].get("framework")
        filed = [x for x in app if fw and _filed(session, x["org_id"], fw, period_label)]
        own = set_by_mandate.get(m["id"])
        due = date.fromisoformat(own["due_date"]) if own else due_date(e, pe)
        ev = {"date": due.isoformat() if due else None, "kind": "obligation", "title": m["short"], "sub": f"{period_label} · {e['deliverable'].get('frequency', 'annual')} · {ch.get('label', e['deliverable'].get('channel'))}",
              "ref_id": own["deadline_id"] if own else None, "status": own["status"] if own else "registry", "overdue": bool(due and due < today and len(filed) < len(app)), "criticality": None,
              "mandate_id": m["id"], "mandate_title": m["title"], "framework": fw, "channel_id": e["deliverable"].get("channel_id"), "channel_kind": ch.get("kind"),
              "due_rule": (e["deliverable"].get("due") or {}).get("label"), "n_applicable": len(app), "n_filed": len(filed), "n_cannot": sum(1 for x in ents if x["status"] != APPLIES and x["missing"]),
              "entities": [{"org_id": x["org_id"], "name": x["name"], "filed": x["org_id"] in {f["org_id"] for f in filed}} for x in app]}
        if due is None:
            undated.append({**ev, "authority": authority})
            continue
        g = groups.setdefault(authority, {"authority": authority, "events": [], "n_deliverables": 0, "n_applicable": 0, "n_filed": 0, "n_overdue": 0, "next_due": None})
        g["events"].append(ev); g["n_deliverables"] += 1; g["n_applicable"] += len(app); g["n_filed"] += len(filed); g["n_overdue"] += int(ev["overdue"])
    for g in groups.values():
        g["events"].sort(key=lambda x: x["date"])
        g["next_due"] = next((x["date"] for x in g["events"] if x["date"] >= today.isoformat()), None)
    auths = sorted(groups.values(), key=lambda g: (g["next_due"] or "9999", g["authority"]))
    events = sorted((ev | {"authority": g["authority"]} for g in auths for ev in g["events"]), key=lambda x: x["date"])
    return {"period_label": period_label, "period_end": pe.isoformat(), "today": today.isoformat(), "authorities": auths, "events": events,
            "upcoming": [e for e in events if e["date"] >= today.isoformat()][:12], "undated": undated,
            "note": "Each deliverable is due to the authority named on its transmission channel in the mandate registry. The date is your own drafted or "
                    "published deadline for the period where you have one, otherwise the act's rule as you apply it. Applicability is judged per entity from "
                    "its regulatory attributes; per-event mandates (no calendar date) are listed separately."}
