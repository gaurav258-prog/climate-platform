"""EBA Pillar 3 ESG — the qualitative disclosure tables (Tables 1, 2 and 3), which the institution authors.

The rows — their letters, headings and wording — come from the governing template specification
(data/reference/regspec/bank_p3esg); nothing is typed here. Authored text is stored per organisation under
'table<n>.<row letter>' (organizations.p3esg_narratives), versioned and attested with the filing.
"""
from __future__ import annotations

from datetime import date

_TABLES = ("TAB1", "TAB2", "TAB3")


def _spec(spec: dict | None) -> dict:
    import services.regspec as R
    return spec or R.governing("bank_p3esg", period_end=date.today())


def valid_keys(spec: dict | None = None) -> set[str]:
    """Every authorable key of the governing tables — a save naming anything else is refused."""
    from services.governance.pillar3_other import qualitative_rows
    s = _spec(spec)
    return {r["key"] for tid in _TABLES for r in qualitative_rows(s, tid)}


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
    return {"tables": out, "total_rows": total, "authored": filled, "spec": s["version"]}
