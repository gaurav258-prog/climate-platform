"""An insurer's document reports — the ORSA climate change scenario analysis (Directive 2009/138/EC Art. 45a, 51(1b)(e))
and the pre-emptive recovery plan's natural-catastrophe stress and capital indicators (Directive (EU) 2025/1 Art. 5(7),
(8)) — built item by item from the governing specification: the printed wording as is, the items the platform computes
(services.governance.orsa_climate / irrd_stress) and the undertaking's own answers (template_answers), for the
undertaking (reporting entity) or group the report is for, and its reporting period.

Both apply to reports made from 30 January 2027 (specification basis: the disclosure date). A report is prepared for its
planned date — an ORSA's conclusion, a plan's submission — which chooses the rules and is frozen with the filing.
"""
from __future__ import annotations

from datetime import date

import services.regspec as R
from services.governance import irrd_stress, orsa_climate
from services.governance import template_answers as TA

DOCS = {
    "insurer_orsa_climate": {"module": orsa_climate, "label": "ORSA — climate change scenario analysis",
                             "who": "the undertaking's own assessment"},
    "insurer_recovery_stress": {"module": irrd_stress, "label": "Pre-emptive recovery plan — nat-cat stress and indicators",
                                "who": "the undertaking's plan"},
}


class DocumentError(ValueError):
    pass


def _doc(report_type: str) -> dict:
    if report_type not in DOCS:
        raise DocumentError(f"'{report_type}' is not an insurer document report")
    return DOCS[report_type]


def spec_for(report_type: str, period_end: date, disclosure_date: date | None = None) -> dict:
    """The governing specification for a report made on disclosure_date (default: today, or — before the rules apply
    — the day they apply, the earliest date such a report can be made under them)."""
    mod = _doc(report_type)["module"]
    first = min(v["applies"]["from"] for v in R.versions(mod.FAMILY) if v["status"] == "adopted")
    on = disclosure_date or max(date.today(), date.fromisoformat(first))
    spec = R.governing(mod.FAMILY, period_end=period_end, disclosure_date=on)
    if spec is None:
        raise DocumentError(f"no adopted {mod.FAMILY} specification governs a report made on {on} (they apply from {first})")
    return spec


def freeze(session, org_id: str, report_type: str, *, entity_ids=None, value_weights=None, translation=None,
           period_end: date) -> dict:
    """What a filing freezes: the computed part and the undertaking's answers, for its entity (or group) and period."""
    from services.governance.entities import root_of
    mod = _doc(report_type)["module"]
    entity = root_of(session, org_id, entity_ids)
    computed = mod.compute(session, org_id, entity_ids=entity_ids, value_weights=value_weights, translation=translation,
                           reporting_entity_id=entity, period_end=period_end)
    answers = TA.read(session, org_id, mod.FAMILY, mod.DOCUMENT, period_end=period_end, entity_id=entity)
    return {"document": mod.DOCUMENT, "family": mod.FAMILY, "period_end": period_end.isoformat(),
            "reporting_entity_id": entity, "computed": computed, "answers": answers}


def build(spec: dict, report_type: str, payload: dict) -> list[dict]:
    """Every item in reading order: printed wording as is; computed items with their value; answered items with the
    undertaking's answer; 'missing' with what is needed. Under the SNCU derogation (Art. 45a(5)) the scenario items
    are not required."""
    mod = _doc(report_type)["module"]
    t = spec["templates"][0]
    b = mod.binding(spec)[t["id"]]["items"]
    answers = payload.get("answers") or {}
    derogation = report_type == "insurer_orsa_climate" and (answers.get("sncu") or {}).get("ticked") is True
    waived = {"scenarios", "scenarios.below_2c", "scenarios.above_2c", "impact", "impact.interval", "review",
              "review.performance"} if derogation else set()
    out = []
    for i in t["items"]:
        row = {k: i.get(k) for k in ("id", "kind", "label", "parent", "instruction", "blank")}
        src = b.get(i["id"])
        if src is None:
            row.update(source="fixed", status="printed")
        elif i["id"] in waived:
            row.update(source=src, value=None, status="printed", needs=None,
                       note="not required: small and non-complex undertaking (Art. 45a(5))")
        elif src == "computed":
            v = mod.computed_value(i["id"], payload.get("computed"))
            row.update(source="computed", value=v, status="filled" if v is not None else "missing",
                       needs=None if v is not None else "the book and the attested Solvency II figures")
        else:
            v = answers.get(i["id"])
            row.update(source="input", value=v, status="filled" if v is not None else "missing",
                       needs=None if v is not None else _doc(report_type)["who"])
        out.append(row)
    return out


def live(session, org_id: str, report_type: str, *, entity_id: str | None, period_end: date,
         disclosure_date: date | None = None) -> dict:
    """The document as it stands now (not frozen): what a filing would hold, for the entity and period."""
    from services.governance.entities import subtree_ids
    spec = spec_for(report_type, period_end, disclosure_date)
    ids = subtree_ids(session, org_id, entity_id) if entity_id else None
    weights = None
    if ids and len(ids) > 1:
        from services.governance.entities import ownership_weights
        weights = ownership_weights(session, org_id, root_entity_id=entity_id, regime="solvency2_method1")
    payload = freeze(session, org_id, report_type, entity_ids=ids, value_weights=weights, period_end=period_end)
    t = spec["templates"][0]
    return {"report_type": report_type, "title": t["title"], "citation": R.citation(spec, t["id"]),
            "spec": {"framework": spec["framework"], "version": spec["version"], "applies": spec["applies"]},
            "period_end": period_end.isoformat(), "reporting_entity_id": entity_id,
            "items": build(spec, report_type, payload), "computed": payload["computed"]}


def save(session, org_id: str, report_type: str, answers: dict, user_id: str, *, entity_id: str | None,
         period_end: date, disclosure_date: date | None = None) -> dict:
    mod = _doc(report_type)["module"]
    spec = spec_for(report_type, period_end, disclosure_date)
    t = spec["templates"][0]
    bad = [k for k, v in (answers or {}).items() if k == "impact.interval" and v and not _interval_ok(v)]
    if bad:
        raise DocumentError("impact.interval: the interval is a number of years, no longer than three (Art. 45a(3))")
    return TA.save(session, org_id, mod.FAMILY, mod.DOCUMENT, t, mod.binding(spec)[t["id"]]["items"], answers, user_id,
                   period_end=period_end, entity_id=entity_id, label=t["title"], computed_from="the book")


def _interval_ok(v: dict) -> bool:
    import re
    m = re.search(r"\d+(\.\d+)?", str((v or {}).get("text") or ""))
    return bool(m) and 0 < float(m.group()) <= 3


# ───────────────────────────── the filing: form sections and checks ─────────────────────────────

def _frozen_spec(payload: dict, report_type: str) -> dict | None:
    mod = _doc(report_type)["module"]
    rec = (payload.get("_specs") or {}).get(mod.FAMILY) or {}
    return R.load(mod.FAMILY, rec["version"]) if rec.get("version") else None


def sections(payload: dict, report_type: str) -> list[dict]:
    spec = _frozen_spec(payload, report_type)
    doc = payload.get("document_report")
    if spec is None or not doc:
        return []
    t = spec["templates"][0]
    built = build(spec, report_type, doc)
    gaps = [i for i in built if i["status"] == "missing"]
    comp = doc.get("computed") or {}
    notes = [f"Capital: {'attested' if (comp.get('capital') or {}).get('attested') else 'not yet attested'} "
             f"(own funds, SCR); reinsurance: {comp.get('treaty_basis')}."]
    if gaps:
        notes.append(f"{len(gaps)} items still need the undertaking's answer — answer them on the report's page and refresh "
                     "this draft.")
    return [{"title": f"{t['title']} ({R.citation(spec, t['id'])})", "key": f"{report_type}_document", "kind": "document",
             "columns": [], "rows": [], "items": built, "note": " ".join(notes),
             "spec": {"framework": spec["framework"], "version": spec["version"], "template": t["id"],
                      "sha256": spec["_sha256"]}}]


def checks(payload: dict, report_type: str) -> list[dict]:
    from services.governance.filing_validation import _f
    spec = _frozen_spec(payload, report_type)
    doc = payload.get("document_report")
    if spec is None or not doc:
        return [_f("specification", "completeness", "blocking", False,
                   "no adopted specification governs this report's disclosure date — set the date it will be made "
                   "(on or after 30 January 2027)")]
    built = build(spec, report_type, doc)
    gaps = [i["id"] for i in built if i["status"] == "missing"]
    comp = doc.get("computed") or {}
    out = [_f("items_answered", "completeness", "blocking", not gaps,
              "every item is computed or answered" if not gaps else "items without an answer: " + ", ".join(gaps[:8])),
           _f("capital_attested", "completeness", "blocking", bool((comp.get("capital") or {}).get("attested")),
              "own funds and SCR are the undertaking's attested Solvency II figures" if (comp.get("capital") or {}).get("attested")
              else "own funds and SCR are not attested for this undertaking and period (Solvency II provided values)"),
           _f("treaty_attested", "completeness", "blocking", comp.get("treaty_basis") == "attested",
              "the attested reinsurance nets the losses" if comp.get("treaty_basis") == "attested"
              else "no attested reinsurance for this undertaking — losses are net of the illustrative programme")]
    interval = (doc.get("answers") or {}).get("impact.interval")
    if report_type == "insurer_orsa_climate" and interval:
        out.append(_f("interval_three_years", "plausibility", "blocking", _interval_ok(interval),
                      "the analysis interval is at most three years (Art. 45a(3))" if _interval_ok(interval)
                      else "the analysis interval must be a number of years no longer than three (Art. 45a(3))"))
    return out
