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

from services.governance.filings import FRAMEWORKS
from services.governance.reg_reference import reference

_COMING_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "crcs" / "coming_changes.json"


def _from_draft_specs() -> list[dict]:
    """A coming change for every draft template specification: what its machine diff against the governing version
    says, in the customer's terms. Never dated unless the draft itself fixes a date."""
    import services.regspec as R
    out = []
    for fw in R.frameworks():
        gov = R.governing(fw, period_end=date.today())
        for d in (s for s in R.versions(fw) if s["status"] == "draft"):
            if gov is None:
                continue
            df = R.diff(gov, d)
            code = {t["id"]: t.get("code") or t["id"] for t in gov["templates"] + d["templates"]}
            parts = []
            if df["templates_removed"]:
                parts.append(f"removes {', '.join(code[t] for t in df['templates_removed'])}")
            if df["templates_added"]:
                parts.append(f"adds {', '.join(code[t] for t in df['templates_added'])}")
            for c in df["changed"]:
                n = {k: sum(len((c.get(a) or {}).get(k) or []) for a in ("rows",)) for k in ("added", "removed", "moved")}
                bits = [f"{v} row(s) {k}" for k, v in n.items() if v]
                if bits:
                    parts.append(f"{code[c['id']]}: {', '.join(bits)}")
            applies = d["applies"].get("from")
            out.append({
                "sectors": list((FRAMEWORKS.get(fw) or {}).get("sectors") or ()), "framework": fw, "affects": [fw],
                "title": f"{(reference(fw) or {}).get('official_name') or fw} — {d['act'].get('short') or d['act']['title']}",
                "date": None,
                "when": "draft · not adopted" + (f" · would apply from {applies}" if applies else " · no application date set"),
                "whats_changing": ("Compared with the version in force: " + "; ".join(parts) + ".") if parts
                                  else "Changes wording or references only.",
                "prepare": None, "data_tbc": "A draft: the templates may change before adoption; exact data needs follow on adoption.",
                "citation": d["act"]["title"], "url": d["act"].get("url"), "spec": d["version"]})
    return out


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
            out.append({"title": c["title"], "when": c["when"], "date": c.get("date"),
                        "citation": c["citation"], "url": c.get("url"), "source": "curated"})
    if session is not None:
        try:
            from services.regulatory_monitoring.eurlex_detector import detected_changes
            for dc in detected_changes(session, framework):
                out.append({"title": dc["title"], "when": (dc["effective_date"] or f"detected {dc['detected_at']}"),
                            "date": dc["effective_date"], "citation": f"EUR-Lex · CELEX:{dc['celex']}",
                            "url": dc["url"], "source": "detected", "status": dc["status"]})
        except Exception:
            pass
    return out


def _short(fw: str) -> str:
    """A one-line 'what it requires' for a framework the org files today."""
    r = reference(fw) or {}
    return r.get("summary") or (FRAMEWORKS.get(fw, {}).get("label") or "")


def outlook(org_type: str | None, session=None, org_id: str | None = None) -> dict:
    """The customer's regulatory outlook: what's in force for this sector today, and what's coming — with the
    coming dates verified live against the EUR-Lex register, plus any changes the live detector has flagged."""
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
        if org_type not in (meta.get("sectors") or ()):
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

    coming = []
    for c in coming_changes():
        if org_type not in (c.get("sectors") or []):
            continue
        item = {k: c[k] for k in ("framework", "title", "date", "when", "whats_changing", "prepare", "citation", "url")}
        item["date_fixed"] = c.get("date") is not None
        item["source"] = "curated"
        item["data_tbc"] = c.get("data_tbc")
        # data-readiness: for each required field, check the client's own book (have / partial / needed)
        fields = []
        for f in (c.get("data_fields") or []):
            row = {"field": f["field"], "note": f.get("note", "")}
            if session is not None and org_id:
                try:
                    from services.governance.reg_readiness import field_readiness
                    row.update(field_readiness(session, org_id, f.get("key")))
                except Exception:
                    row["status"] = "needed"
            fields.append(row)
        item["data_fields"] = fields
        if session is not None and org_id and fields:
            item["data_summary"] = {"have": sum(1 for f in fields if f.get("status") == "have"),
                                    "partial": sum(1 for f in fields if f.get("status") == "partial"),
                                    "needed": sum(1 for f in fields if f.get("status") == "needed"),
                                    "total": len(fields)}
        # reconcile the curated date against the live EUR-Lex register — only for items that (a) carry a fixed
        # date and (b) are tied to a single governing act, so we compare like with like (not a sub-timeline).
        fw = c.get("framework")
        v = verified.get(fw) if fw else None
        if v and v.get("next_effective") and item["date_fixed"]:
            item["verified_date"] = v["next_effective"]
            item["verified_at"] = v.get("checked_at")
            if item["date"] != v["next_effective"]:
                item["date_moved"] = True   # our curated date differed from the register
                item["date"] = v["next_effective"]
        coming.append(item)
    # auto-detected changes from the live scan → new "pending review" items
    for dc in detected:
        # only surface those relevant to this sector's frameworks
        if not any(dc["framework"] in (c.get("affects") or []) or dc["framework"] == c.get("framework")
                   for c in coming_changes() if org_type in (c.get("sectors") or [])) \
           and dc["framework"] not in [f for f in FRAMEWORKS if org_type in (FRAMEWORKS[f].get("sectors") or ())]:
            continue
        coming.append({"framework": dc["framework"], "title": dc["title"], "date": dc["effective_date"],
                       "date_fixed": dc["effective_date"] is not None, "when": (dc["effective_date"] or "newly detected"),
                       "whats_changing": dc["summary"], "prepare": None, "data_fields": [], "data_tbc": None,
                       "citation": f"EUR-Lex · CELEX:{dc['celex']}", "url": dc["url"],
                       "source": "detected", "status": dc["status"], "detected_at": dc["detected_at"]})
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
                        "n_prepare": sum(1 for c in coming if c.get("prepare")),
                        "n_dated": sum(1 for c in coming if c["date_fixed"]),
                        "n_detected": sum(1 for c in coming if c.get("source") == "detected"),
                        "n_verified": sum(1 for c in coming if c.get("verified_date"))}}
