"""Regulatory outlook — the CUSTOMER's view of the regulation itself.

Strictly customer point-of-view: what applies to you today, what regulatory changes are coming (and when),
and whether YOU will need to provide new data or an integration. It says nothing about Tellumen's own build
process — that internal delivery pipeline lives elsewhere. Dates and citations are real; where a change is
proposed but not final, it says so rather than inventing a date.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from core import messages
from services.governance.filings import FRAMEWORKS
from services.governance.reg_reference import reference

_COMING_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "crcs" / "coming_changes.json"


def _day(iso: str | None) -> str | None:
    """'2026-12-30' → '30 December 2026' (the words a message shows)."""
    if not iso:
        return None
    d = date.fromisoformat(str(iso)[:10])
    return f"{d.day} {d.strftime('%B %Y')}"


def _name(fw: str | None) -> str | None:
    """A framework's official name (data/reference via reg_reference), else its filing label."""
    if not fw:
        return None
    return (reference(fw) or {}).get("official_name") or (FRAMEWORKS.get(fw) or {}).get("label")


def _from_draft_specs() -> list[dict]:
    """A coming change for every draft template specification: what its machine diff against the governing version
    counts, told by a catalogue message. Never dated unless the draft itself fixes a date."""
    import services.regspec as R
    out = []
    for fw in R.frameworks():
        gov = R.governing(fw, period_end=date.today())
        for d in (s for s in R.versions(fw) if s["status"] == "draft"):
            if gov is None:
                continue
            df = R.diff(gov, d)
            counts = {"added": len(df["templates_added"]), "removed": len(df["templates_removed"]), "changed": len(df["changed"]),
                      "unchanged": len(df["unchanged"]),
                      "rows_added": sum(len((c.get("rows") or {}).get("added") or []) for c in df["changed"]),
                      "rows_removed": sum(len((c.get("rows") or {}).get("removed") or []) for c in df["changed"])}
            name = R.family_name(fw)
            code = "regchange.draft.templates" if counts["added"] or counts["removed"] or counts["changed"] else "regchange.draft.wording"
            msg = messages.render(code, name=name, added=counts["added"], removed=counts["removed"], changed=counts["changed"])
            governs = R.report_types_of(fw) or [fw]           # a family reaches the sectors of the report types it governs
            out.append({
                "sectors": sorted({sec for rt in governs for sec in (FRAMEWORKS.get(rt) or {}).get("sectors") or ()}),
                "framework": fw if fw in FRAMEWORKS else governs[0], "affects": governs,
                "title": name, "name": name, "date": None, "when": msg["label"],
                "would_apply_from": d["applies"].get("from"), "whats_changing": None, "message": msg, "draft": counts,
                "prepare": None, "data_tbc": None,
                "citation": d["act"]["title"], "url": d["act"].get("url"), "spec": d["version"]})
    return out


def _detected_item(session, dc: dict) -> dict:
    """A change the live EUR-Lex detector recorded, told from the register's own facts: which act, and whether it
    replaces or amends the act the framework is filed under, or the act's own dates moved (services.regulatory_
    monitoring.eurlex_detector). The detector's stored sentence is kept for the alert task, not shown."""
    from sqlalchemy import text

    from services.governance.reg_versions import short_title
    from services.regulatory_monitoring.eurlex_detector import FRAMEWORK_CELEX
    from services.regulatory_monitoring.tracked_acts import act_meta
    tracked = FRAMEWORK_CELEX.get(dc["framework"]) or []
    rel = session.execute(text("""SELECT relation, title FROM reg_act_relation WHERE related_celex = :c AND celex = ANY(:t)
                                  ORDER BY relation = 'amends' LIMIT 1"""), {"c": dc["celex"], "t": tracked}).mappings().first()
    name = _name(dc["framework"]) or dc["framework"]
    if rel is not None:
        code, act = ("regchange.detected.amended" if rel["relation"] == "amends" else "regchange.detected.replaced",
                     short_title(rel["title"], dc["celex"]))
    elif dc["celex"] in tracked:
        code, act = "regchange.detected.dates", act_meta(dc["celex"])["title"]
    else:
        code, act = None, None
    msg = messages.render(code, act=act, name=name, detected=_day(dc["detected_at"])) if code else None
    return {"framework": dc["framework"], "title": name, "name": name, "date": dc["effective_date"],
            "date_fixed": dc["effective_date"] is not None,
            "when": dc["effective_date"] or (msg["label"] if msg else None),
            "whats_changing": dc["summary"], "message": msg, "prepare": None, "data_fields": [], "data_tbc": None,
            "citation": act or f"EUR-Lex · CELEX:{dc['celex']}", "url": dc["url"],
            "source": "detected", "status": dc["status"], "detected_at": dc["detected_at"]}


def coming_changes() -> list[dict]:
    """Every coming change: the curated register (data/reference/crcs/coming_changes.json) and one per draft spec."""
    return json.loads(_COMING_FILE.read_text())["changes"] + _from_draft_specs()

def changes_affecting(org_type: str | None, framework: str, session=None) -> list[dict]:
    """Coming changes (for this sector) that touch a given framework — the single signal both the customer
    outlook and the supervisory-question 'review recommended' flags read from. Combines the curated library
    with anything the live EUR-Lex detector has flagged for this framework (session required for the latter)."""
    out = []
    for c in coming_changes():
        if org_type not in (c.get("sectors") or []):
            continue
        if c.get("framework") == framework or framework in (c.get("affects") or []):
            out.append({"title": c["title"], "when": c["when"], "date": c.get("date"), "message": c.get("message"),
                        "citation": c["citation"], "url": c.get("url"), "source": "curated"})
    if session is not None:
        try:
            from services.regulatory_monitoring.eurlex_detector import detected_changes
            for dc in detected_changes(session, framework):
                it = _detected_item(session, dc)
                out.append({k: it[k] for k in ("title", "when", "date", "message", "citation", "url", "source", "status")})
        except Exception:
            pass
    return out


def _short(fw: str) -> str:
    """A one-line 'what it requires' for a framework the org files today."""
    r = reference(fw) or {}
    return r.get("summary") or (FRAMEWORKS.get(fw, {}).get("label") or "")


def _phase(day: str | None) -> tuple[str, int | None]:
    """Where a change's date stands today: ('in_force', days since <0) once it has passed, ('dated', days to go) while
    ahead, ('undated', None) while the act sets no date."""
    if not day:
        return "undated", None
    days = (date.fromisoformat(day[:10]) - date.today()).days
    return ("in_force" if days < 0 else "dated"), days


def _field(f: dict, readiness: dict) -> dict:
    """One field a change asks for, with what the client's own data holds of it, and the message that says so."""
    held, total, status = readiness.get("held"), readiness.get("total"), readiness.get("status", "needed")
    code = ("regchange.field.not_read" if held is None or total is None else "regchange.field.none_on_file" if total == 0
            else {"have": "regchange.field.have", "partial": "regchange.field.partial"}.get(status, "regchange.field.missing"))
    return {"field": f["field"], "guidance": f.get("note") or None, "status": status, "held": held, "total": total,
            "message": messages.render(code, held=held, total=total)}


def outlook(org_type: str | None, session=None, org_id: str | None = None) -> dict:
    """The customer's regulatory outlook: what's in force for this sector today, and what's coming — with the
    coming dates verified live against the EUR-Lex register, plus any changes the live detector has flagged. Every
    explanation is a catalogue message (core/messages.py); each change carries its phase by its date today."""
    # live-verified legal dates + auto-detected changes from the EUR-Lex (Cellar) detector
    verified: dict = {}
    detected: list[dict] = []
    checked_at = None
    if session is not None:
        try:
            from services.regulatory_monitoring.eurlex_detector import (
                detected_changes,
                verified_dates,
            )
            verified = verified_dates(session)
            detected = detected_changes(session)
            checked_at = next((v.get("checked_at") for v in verified.values() if v.get("checked_at")), None)
        except Exception:
            verified, detected = {}, []

    in_force = []
    for fw, meta in FRAMEWORKS.items():
        if org_type not in (meta.get("sectors") or ()) or meta.get("retired"):    # a retired report is no longer owed
            continue
        ref = reference(fw) or {}
        in_force.append({
            "framework": fw,
            "name": ref.get("official_name") or meta.get("label"),
            "authority": ref.get("authority") or meta.get("regulator"),
            "frequency": meta.get("frequency"),
            "requires": _short(fw),
            "citation": ref.get("legal_basis") or meta.get("basis"),
            "url": ref.get("url"),
        })
    in_force.sort(key=lambda x: x["name"] or "")

    def _readiness(key):
        from services.governance.reg_readiness import field_readiness
        try:
            return field_readiness(session, org_id, key)
        except Exception:                       # a read that failed is a field we cannot confirm, never one held
            return {"status": "needed", "held": None, "total": None}
    readiness = _readiness if session is not None and org_id else None

    coming = []
    for c in coming_changes():
        if org_type not in (c.get("sectors") or []):
            continue
        item = {k: c.get(k) for k in ("framework", "title", "date", "when", "whats_changing", "prepare", "citation", "url",
                                      "data_tbc", "message", "draft", "would_apply_from")}
        item["name"] = c.get("name") or _name(c.get("framework"))
        item["date_fixed"] = c.get("date") is not None
        item["source"] = "draft" if c.get("spec") else "curated"
        # data-readiness: for each required field, check the client's own book (have / partial / needed)
        fields = [_field(f, readiness(f.get("key")) if readiness else {"status": "needed"}) for f in (c.get("data_fields") or [])]
        item["data_fields"] = fields
        if readiness and fields:
            item["data_summary"] = {"have": sum(1 for f in fields if f["status"] == "have"),
                                    "partial": sum(1 for f in fields if f["status"] == "partial"),
                                    "needed": sum(1 for f in fields if f["status"] == "needed"),
                                    "total": len(fields)}
        # reconcile the curated date against the live EUR-Lex register — only for items that (a) carry a fixed
        # date and (b) are tied to a single governing act, so we compare like with like (not a sub-timeline).
        fw = c.get("framework")
        v = verified.get(fw) if fw else None
        if v and v.get("next_effective") and item["date_fixed"]:
            item["verified_date"] = v["next_effective"]
            item["verified_at"] = v.get("checked_at")
            item["verified"] = messages.render("regchange.date.verified", checked=_day(v.get("checked_at")))
            if item["date"] != v["next_effective"]:
                item["date_moved"] = True   # our curated date differed from the register
                item["date"] = v["next_effective"]
                item["verified"] = messages.render("regchange.date.moved", date=_day(item["date"]))
        coming.append(item)
    # auto-detected changes from the live scan → new "pending review" items
    applicable = [f for f in FRAMEWORKS if org_type in (FRAMEWORKS[f].get("sectors") or ()) and not FRAMEWORKS[f].get("retired")]
    for dc in detected:
        # only surface those relevant to this sector's frameworks
        if not any(dc["framework"] in (c.get("affects") or []) or dc["framework"] == c.get("framework")
                   for c in coming_changes() if org_type in (c.get("sectors") or [])) \
           and dc["framework"] not in applicable:
            continue
        coming.append(_detected_item(session, dc))
    for it in coming:
        it["phase"], it["days"] = _phase(it.get("date"))
        it["phase_message"] = messages.render(f"regchange.phase.{it['phase']}", date=_day(it.get("date")))
        if not (it.get("prepare") or it.get("data_tbc") or it.get("data_fields") or it["source"] != "curated"):
            it["data_message"] = messages.render("regchange.data.none")
    # per-org impact (deadline urgency + record scope) on every coming change, from the client's own book
    if session is not None and org_id:
        try:
            from services.governance.reg_impact import change_impact
            for it in coming:
                imp = change_impact(session, org_id, it.get("framework"), it.get("date"))
                if imp:
                    it["impact"] = imp
        except Exception:
            pass
    # confirmed exact dates first, chronologically; then the not-yet-fixed ones
    coming.sort(key=lambda c: (c["date"] is None, c["date"] or "9999"))
    return {"in_force": in_force, "coming": coming, "checked_at": checked_at,
            "summary": {"n_in_force": len(in_force), "n_coming": len(coming),
                        "n_ahead": sum(1 for c in coming if c["phase"] != "in_force"),
                        "n_took_effect": sum(1 for c in coming if c["phase"] == "in_force"),
                        "n_prepare": sum(1 for c in coming if c.get("prepare")),
                        "n_dated": sum(1 for c in coming if c["date_fixed"]),
                        "n_detected": sum(1 for c in coming if c.get("source") == "detected"),
                        "n_verified": sum(1 for c in coming if c.get("verified_date"))}}
