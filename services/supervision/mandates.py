"""Regulatory mandate registry — who is regulated, by which article, what they must deliver, through which channel,
by when, and how the act has changed.

Configuration, not code: data/reference/regulatory_mandates.json. Criteria are evaluated over entity attributes
(organisation record + the entity's regulatory attributes). A missing attribute yields 'cannot determine' with the
list of what is missing — never a guess. Each supervisory body can disable a mandate or adapt its criteria and
due rule (supervisor_mandate_setting) and must acknowledge each new version of an act (audited).
Change detection: the acts' CELEX ids are watched by the EUR-Lex detector; a detected change on a mandate's act
is surfaced next to its versions until reviewed.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "regulatory_mandates.json"
APPLIES, NOT_APPLICABLE, CANNOT = "applies", "not_applicable", "cannot_determine"
STATUS_LABEL = {APPLIES: "Applies", NOT_APPLICABLE: "Does not apply", CANNOT: "Cannot determine"}


@lru_cache(maxsize=1)
def registry() -> dict:
    d = json.loads(REGISTRY_PATH.read_text())
    return {"version": d["version"], "attributes": {k: v for k, v in d["attributes"].items() if not k.startswith("_")},
            "jurisdiction_groups": d["jurisdiction_groups"], "mandates": d["mandates"],
            "reminders": {k: v for k, v in (d.get("reminders") or {}).items() if not k.startswith("_")},
            "correspondence": {k: v for k, v in (d.get("correspondence") or {}).items() if not k.startswith("_")},
            "channels": {k: v for k, v in (d.get("channels") or {}).items() if not k.startswith("_")},
            "remittance": {k: v for k, v in (d.get("remittance") or {}).items() if not k.startswith("_")}}


def mandates_for(sectors: list[str]) -> list[dict]:
    return [m for m in registry()["mandates"] if any(s in m["sectors"] for s in sectors)]


def mandate(mandate_id: str) -> Optional[dict]:
    return next((m for m in registry()["mandates"] if m["id"] == mandate_id), None)


# ── entity attributes ────────────────────────────────────────────────────────────────────────────────────────
def entity_attributes(session, org_id: str) -> dict[str, dict]:
    """attribute → {value, source, as_of}. Organisation-record fields first, then the entity's regulatory attributes."""
    org = session.execute(text("SELECT type, country, employees, aum_eur FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).mappings().first()
    out: dict[str, dict] = {}
    if org:
        out["sector"] = {"value": org["type"], "source": "organisation record", "as_of": None}
        out["jurisdiction"] = {"value": org["country"], "source": "organisation record", "as_of": None}
        if org["employees"] is not None:
            out["employees"] = {"value": float(org["employees"]), "source": "organisation record", "as_of": None}
        if org["aum_eur"] is not None:
            out["aum_eur"] = {"value": float(org["aum_eur"]), "source": "organisation record", "as_of": None}
    for r in session.execute(text("SELECT attribute, value_num, value_text, value_bool, as_of, source FROM org_regulatory_attribute WHERE org_id = CAST(:o AS uuid)"),
                             {"o": org_id}).mappings().all():
        v = r["value_bool"] if r["value_bool"] is not None else (r["value_num"] if r["value_num"] is not None else r["value_text"])
        out[r["attribute"]] = {"value": v, "source": r["source"], "as_of": r["as_of"].isoformat() if r["as_of"] else None}
    return out


def set_attribute(session, org_id: str, attribute: str, value: Any, *, source: str, by_user_id: Optional[str], as_of: Optional[str] = None) -> None:
    spec = registry()["attributes"].get(attribute)
    if not spec:
        raise KeyError(attribute)
    num = txt = boo = None
    if spec["type"] == "number":
        num = float(value)
    elif spec["type"] == "bool":
        boo = bool(value) if not isinstance(value, str) else value.strip().lower() in ("true", "yes", "1")
    else:
        txt = str(value)
    session.execute(text("""
        INSERT INTO org_regulatory_attribute (org_id, attribute, value_num, value_text, value_bool, as_of, source, updated_by, updated_at)
        VALUES (CAST(:o AS uuid), :a, :n, :t, :b, CAST(:d AS date), :s, CAST(:u AS uuid), now())
        ON CONFLICT (org_id, attribute) DO UPDATE SET value_num = EXCLUDED.value_num, value_text = EXCLUDED.value_text, value_bool = EXCLUDED.value_bool,
            as_of = EXCLUDED.as_of, source = EXCLUDED.source, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"o": org_id, "a": attribute, "n": num, "t": txt, "b": boo, "d": as_of, "s": source, "u": by_user_id})


# ── criteria ─────────────────────────────────────────────────────────────────────────────────────────────────
def _test(cond: dict, attrs: dict[str, dict]) -> Optional[bool]:
    """True / False, or None when the attribute is missing."""
    a = attrs.get(cond["attribute"])
    if a is None or a.get("value") is None:
        return None
    v, op, want = a["value"], cond["op"], cond["value"]
    if op == "in":
        return v in want
    if op == "in_group":
        return v in registry()["jurisdiction_groups"].get(want, [])
    if op == "==":
        return v == want
    if op == ">":
        return float(v) > float(want)
    if op == ">=":
        return float(v) >= float(want)
    if op == "<":
        return float(v) < float(want)
    if op == "<=":
        return float(v) <= float(want)
    raise ValueError(f"unknown operator {op}")


def evaluate(m: dict, attrs: dict[str, dict]) -> dict:
    """→ {status, missing:[attribute], failed:[label], tier:{label, frequency} | None, checks:[{label, result}]}."""
    checks, missing, failed = [], [], []
    for c in m["criteria"].get("all_of", []):
        r = _test(c, attrs)
        checks.append({"label": c["label"], "attribute": c["attribute"], "result": r})
        if r is None:
            missing.append(c["attribute"])
        elif r is False:
            failed.append(c["label"])
    if failed:
        return {"status": NOT_APPLICABLE, "missing": [], "failed": failed, "tier": None, "checks": checks}
    if missing:
        return {"status": CANNOT, "missing": sorted(set(missing)), "failed": [], "tier": None, "checks": checks}
    tier = None
    for t in m["criteria"].get("tiers", []):
        results = [_test(c, attrs) for c in t["all_of"]]
        for c, r in zip(t["all_of"], results):
            checks.append({"label": c["label"], "attribute": c["attribute"], "result": r, "tier": t["label"]})
        if any(r is None for r in results):
            return {"status": CANNOT, "missing": sorted({c["attribute"] for c, r in zip(t["all_of"], results) if r is None}), "failed": [],
                    "tier": None, "checks": checks}
        if all(results):
            tier = {"label": t["label"], "frequency": t.get("frequency")}
            break
    return {"status": APPLIES, "missing": [], "failed": [], "tier": tier, "checks": checks}


def due_date(m: dict, period_end: date) -> Optional[date]:
    d = m["deliverable"].get("due") or {}
    rule = d.get("rule")
    if rule in ("with_annual_report",) and d.get("months_after_period_end"):
        mth = period_end.month + int(d["months_after_period_end"])
        yr = period_end.year + (mth - 1) // 12
        return date(yr, (mth - 1) % 12 + 1, min(period_end.day, 28))
    if rule in ("weeks_after_period_end", "weeks_after_orsa") and d.get("weeks_after_period_end"):
        return period_end + timedelta(weeks=int(d["weeks_after_period_end"]))
    if rule == "fixed_date":
        return date(period_end.year + 1, int(d["month"]), int(d["day"]))
    return None


# ── per-authority settings, versions, detection ──────────────────────────────────────────────────────────────
def settings(session, reg_org_id: str) -> dict[str, dict]:
    rows = session.execute(text("SELECT mandate_id, enabled, overrides, note, updated_at FROM supervisor_mandate_setting WHERE regulator_org_id = CAST(:r AS uuid)"),
                           {"r": reg_org_id}).mappings().all()
    return {r["mandate_id"]: {"enabled": r["enabled"], "overrides": r["overrides"] or {}, "note": r["note"], "updated_at": r["updated_at"].isoformat()} for r in rows}


def effective(m: dict, setting: Optional[dict]) -> dict:
    """The mandate as this authority applies it: registry entry + its overrides (criteria thresholds, due rule)."""
    e = deepcopy(m)
    ov = (setting or {}).get("overrides") or {}
    for c in e["criteria"].get("all_of", []):
        if c["attribute"] in ov.get("thresholds", {}):
            c["value"] = ov["thresholds"][c["attribute"]]; c["label"] += " (adapted by the authority)"
    for t in e["criteria"].get("tiers", []):
        for c in t["all_of"]:
            if c["attribute"] in ov.get("thresholds", {}):
                c["value"] = ov["thresholds"][c["attribute"]]; c["label"] += " (adapted by the authority)"
    if ov.get("due"):
        e["deliverable"]["due"] = {**e["deliverable"]["due"], **ov["due"], "label": ov["due"].get("label") or e["deliverable"]["due"].get("label")}
    e["enabled"] = (setting or {}).get("enabled", True)
    return e


def acknowledgements(session, reg_org_id: str) -> dict[tuple[str, str], dict]:
    rows = session.execute(text("""SELECT a.mandate_id, a.version, a.acknowledged_at, a.note, u.full_name FROM supervisor_mandate_version_ack a
                                   LEFT JOIN users u ON u.user_id = a.acknowledged_by WHERE a.regulator_org_id = CAST(:r AS uuid)"""), {"r": reg_org_id}).mappings().all()
    return {(r["mandate_id"], r["version"]): {"at": r["acknowledged_at"].isoformat(), "by": r["full_name"], "note": r["note"]} for r in rows}


def detection(session, celex_ids: list[str]) -> dict:
    """What the EUR-Lex detector holds for these acts: last check and any pending detected change."""
    if not celex_ids:
        return {"checked_at": None, "changes": []}
    snaps = session.execute(text("SELECT celex, checked_at FROM reg_source_snapshot WHERE celex = ANY(CAST(:c AS text[]))"), {"c": celex_ids}).mappings().all()
    changes = session.execute(text("""SELECT change_id::text AS change_id, celex, title, summary, effective_date, status, url, detected_at
                                      FROM reg_detected_change WHERE celex = ANY(CAST(:c AS text[])) ORDER BY detected_at DESC"""), {"c": celex_ids}).mappings().all()
    return {"checked_at": max((s["checked_at"] for s in snaps), default=None).isoformat() if snaps else None,
            "watched": sorted({s["celex"] for s in snaps}),
            "changes": [dict(c) | {"effective_date": c["effective_date"].isoformat() if c["effective_date"] else None, "detected_at": c["detected_at"].isoformat()} for c in changes]}


def registry_view(session, reg_org_id: str, cfg: dict) -> dict:
    sectors = list(cfg["sectors"].keys())
    st, acks = settings(session, reg_org_id), acknowledgements(session, reg_org_id)
    out = []
    for m in mandates_for(sectors):
        e = effective(m, st.get(m["id"]))
        versions = [{**v, "acknowledged": acks.get((m["id"], v["version"]))} for v in m["versions"]]
        latest = m["versions"][-1]["version"] if m["versions"] else None
        out.append({**e, "versions": versions, "latest_version": latest,
                    "latest_acknowledged": bool(acks.get((m["id"], latest))) if latest else True,
                    "detection": detection(session, m.get("detection_celex") or []),
                    "setting": st.get(m["id"])})
    return {"registry_version": registry()["version"], "attributes": registry()["attributes"], "mandates": out,
            "n_unacknowledged": sum(1 for x in out if not x["latest_acknowledged"]),
            "note": "Excerpts are curated digests of the cited article; the linked act on EUR-Lex is authoritative. Criteria read the "
                    "entity's attributes; a missing attribute gives 'cannot determine', never a guess."}


def population_view(session, reg_org_id: str, entities: list[dict], cfg: dict, period_end: date) -> dict:
    st = settings(session, reg_org_id)
    ms = [effective(m, st.get(m["id"])) for m in mandates_for(list(cfg["sectors"].keys()))]
    ms = [m for m in ms if m["enabled"]]
    rows = []
    for e in entities:
        attrs = entity_attributes(session, e["org_id"])
        cells = []
        for m in ms:
            if e["type"] not in m["sectors"]:
                continue
            ev = evaluate(m, attrs)
            d = due_date(m, period_end) if ev["status"] == APPLIES else None
            cells.append({"mandate_id": m["id"], "short": m["short"], "framework": m["deliverable"].get("framework"), "binding": m["binding"],
                          **ev, "status_label": STATUS_LABEL[ev["status"]], "due_date": d.isoformat() if d else None,
                          "channel": m["deliverable"]["channel"], "direction": m["deliverable"]["direction"]})
        rows.append({"org_id": e["org_id"], "name": e["name"], "type": e["type"], "country": e.get("country"),
                     "attributes": {k: v for k, v in attrs.items()}, "mandates": cells,
                     "n_applies": sum(1 for c in cells if c["status"] == APPLIES), "n_cannot": sum(1 for c in cells if c["status"] == CANNOT),
                     "missing": sorted({a for c in cells for a in c["missing"]})})
    return {"period_end": period_end.isoformat(), "mandates": [{"id": m["id"], "short": m["short"], "title": m["title"], "sectors": m["sectors"]} for m in ms],
            "entities": rows, "attributes": registry()["attributes"],
            "summary": {"entities": len(rows), "cannot_determine": sum(1 for r in rows if r["n_cannot"]), "attributes_missing": sum(len(r["missing"]) for r in rows)}}
