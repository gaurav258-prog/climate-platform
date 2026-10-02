"""EBA Pillar 3 ESG — the qualitative disclosure tables (Tables 1, 2 and 3), which the institution authors.

The rows — their letters, headings and wording — come from the governing template specification
(data/reference/regspec/bank_p3esg); nothing is typed here. Authored text belongs to one institution and one disclosure
reference date: the answers to family 'bank_p3esg', document 'qualitative', in the one store of template answers
(services.governance.template_answers), keyed by the reporting entity (none: the organisation itself) and the reference
date, under 'table<n>.<row letter>'. A filing freezes the text of its own undertaking and reference date with its
figures (pillar3_report.freeze: payload 'qualitative'), prints it, and is blocked while a row is unanswered.

The narrative accompanying Template 1 (columns i–k: data sources, methodology, which kinds of emissions, the plans) is
answered in the same store and the same keys under 't1.<item>' (items and their quoted basis:
services.governance.pillar3_t1); a filing freezes it, and validation requires the items the institution's statements
call for.

Text stored before answers were keyed (no undertaking, no date) is shown for reference only — never frozen or printed.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from services.governance import template_answers as T

_TABLES = ("TAB1", "TAB2", "TAB3")
FAMILY, DOCUMENT = "bank_p3esg", "qualitative"


def _spec(spec: dict | None) -> dict:
    import services.regspec as R
    return spec or R.governing("bank_p3esg", period_end=date.today())


def valid_keys(spec: dict | None = None) -> set[str]:
    """Every authorable key of the governing tables — a save naming anything else is refused."""
    from services.governance.pillar3_other import qualitative_rows
    from services.governance.pillar3_t1 import narrative_items
    s = _spec(spec)
    return {r["key"] for tid in _TABLES for r in qualitative_rows(s, tid)} | {n["key"] for n in narrative_items()}


def _t1_narrative(saved: dict) -> dict:
    """The narrative accompanying Template 1 (Annex XL, columns i-k): each item with the quoted instruction that asks
    for it and the statements under which it is required (services.governance.pillar3_t1)."""
    from services.governance.pillar3_t1 import narrative_items, quote, reference
    opts = reference()["statements"]["p3esg_t1_emissions_estimation"]["options"]
    rows = [{"key": n["key"], "row": "T1", "group": "Template 1 — narrative accompanying the template",
             "prompt": n["prompt"], "value": saved.get(n["key"]) or "",
             "basis": " ".join(quote(q) for q in n["quotes"]),
             "required_when": "Required when you state: " + "; ".join(f"'{o}'" for o in n["required_when"] if o in opts)}
            for n in narrative_items()]
    return {"table": "T1N", "title": "Template 1 — narrative accompanying the template (columns i–k)",
            "ref": "Annex XL, Template 1, columns i–k", "rows": rows}


def qualitative_structure(saved: dict | None, spec: dict | None = None) -> dict:
    """The three qualitative tables with the institution's authored text merged in, and a completion count."""
    import services.regspec as R
    from services.governance.pillar3_other import qualitative_rows
    s = _spec(spec)
    saved = saved or {}
    out, total, filled = [], 0, 0
    for tid in _TABLES:
        t = R.template(s, tid)
        rows = []
        for r in qualitative_rows(s, tid):
            val = saved.get(r["key"]) or ""
            total += 1
            filled += bool(val.strip())
            rows.append({**r, "value": val})
        out.append({"table": tid, "title": t["title"], "ref": R.citation(s, tid), "rows": rows})
    t1 = _t1_narrative(saved)
    out.append(t1)
    total += len(t1["rows"])
    filled += sum(1 for r in t1["rows"] if r["value"].strip())
    return {"tables": out, "total_rows": total, "authored": filled, "spec": s["version"]}


def read(session: Session, org_id: str, entity_id: str | None, period_end: date) -> dict:
    """{row key: authored text} of one institution's qualitative tables for one reference date."""
    return {k: v["text"] for k, v in T.read(session, org_id, FAMILY, DOCUMENT, entity_id=entity_id,
                                            period_end=period_end).items() if v.get("text")}


def earlier(session: Session, org_id: str) -> dict:
    """Text stored before answers were keyed by undertaking and reference date — for reference only."""
    return {k: v["text"] for k, v in T.read(session, org_id, FAMILY, DOCUMENT).items() if v.get("text")}


def save(session: Session, org_id: str, values: dict[str, str], user_id: str | None, *, entity_id: str | None,
         period_end: date, spec: dict | None = None) -> dict:
    """Store authored text per row of the governing tables for one institution and reference date (a blank text clears
    the row); {saved, refused}."""
    keys = valid_keys(spec)
    template = {"items": [{"id": k, "kind": "field"} for k in keys]}
    answers = {k: {"text": v} if isinstance(v, str) and v.strip() else None for k, v in values.items()}
    return T.save(session, org_id, FAMILY, DOCUMENT, template, dict.fromkeys(keys, "input"), answers, user_id,
                  entity_id=entity_id, period_end=period_end, label="the governing Pillar 3 ESG qualitative tables")


def frozen(session: Session, org_id: str, entity_id: str | None, period_end: date, spec: dict) -> dict:
    """What a filing freezes: the text of Tables 1-3 for its undertaking and reference date."""
    from services.governance.pillar3_other import qualitative_rows
    text_ = read(session, org_id, entity_id, period_end)
    keys = [r["key"] for tid in _TABLES for r in qualitative_rows(spec, tid)]
    return {"entity_id": entity_id, "reference_date": period_end.isoformat(), "rows": {k: text_[k] for k in keys if k in text_}}


def unanswered(spec: dict, q: dict) -> list[str]:
    """The rows of Tables 1-3 a frozen filing has no text for (each 'Table <n> <row>')."""
    from services.governance.pillar3_other import qualitative_rows
    rows = (q or {}).get("rows") or {}
    return [f"Table {tid[-1]} {r['row']}" for tid in _TABLES for r in qualitative_rows(spec, tid) if not (rows.get(r["key"]) or "").strip()]
