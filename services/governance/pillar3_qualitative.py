"""EBA Pillar 3 ESG — the qualitative disclosure tables (Tables 1, 2 and 3), which the institution authors.

The rows — their letters, headings and wording — come from the governing template specification
(data/reference/regspec/bank_p3esg); nothing is typed here. Authored text is stored per organisation under
'table<n>.<row letter>' — the organisation's answers to family 'bank_p3esg', document 'qualitative', in the one store of
template answers (services.governance.template_answers) — versioned and attested with the filing.

The narrative accompanying Template 1 (columns i–k: data sources, methodology, which kinds of emissions, the plans) is
answered in the same store under 't1.<item>' (items and their quoted basis: services.governance.pillar3_t1); a filing
freezes it, and validation requires the items the institution's statements call for.
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


def read(session: Session, org_id: str) -> dict:
    """{row key: authored text} of the organisation's qualitative tables."""
    return {k: v["text"] for k, v in T.read(session, org_id, FAMILY, DOCUMENT).items() if v.get("text")}


def save(session: Session, org_id: str, values: dict[str, str], user_id: str | None, spec: dict | None = None) -> dict:
    """Store authored text per row of the governing tables (a blank text clears the row); {saved, refused}."""
    keys = valid_keys(spec)
    template = {"items": [{"id": k, "kind": "field"} for k in keys]}
    answers = {k: {"text": v} if isinstance(v, str) and v.strip() else None for k, v in values.items()}
    return T.save(session, org_id, FAMILY, DOCUMENT, template, dict.fromkeys(keys, "input"), answers, user_id,
                  label="the governing Pillar 3 ESG qualitative tables")
