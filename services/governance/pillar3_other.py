"""Pillar 3 Templates 3, 4 and 10 and qualitative Tables 1-3, bound to the governing template specification.

Rows, columns and wording come from the spec; this module says how each is filled.
  T3   alignment metrics per IEA sector: gross carrying amount and the portfolio intensity from the transition-alignment
       engine; the institution's own target (column g) is supplied. Row 9 is the template's open row for further sectors.
  T4   exposures to the top 20 carbon-intensive firms, aggregated into the template's single row.
  T10  other climate-mitigating actions: every figure is supplied by the institution (bonds and loans under standards
       other than the EU's are not on the loan tape) — the template's fixed rows, each cell entered for the reporting
       period as a supplied value ('input:cell') and attested under four eyes (services/governance/provided_data).
Binding sources: 'input:cell' = a value entered for that cell; any other 'input:<fact>' = aggregated from a per-exposure
fact on the loan tape, never typed into the template.
  Tables 1-3  narrative the institution authors, per printed row letter.
"""
from __future__ import annotations

import re

# which transition-alignment engine sectors each Template 3 row holds (row 2 'Fossil fuel combustion' = oil & gas + coal)
T3_SECTORS: dict[str, list[str]] = {"1": ["power"], "2": ["oil_gas", "coal"], "3": ["automotive"], "4": ["aviation"],
                                    "5": ["maritime"], "6": ["cement"], "7": ["iron_steel"], "8": ["chemicals"], "9": []}

def _tab(spec: dict, tid: str) -> dict:
    from services.regspec import template
    t = template(spec, tid)
    return {"rows": {r["id"]: ("n/a" if r["id"].startswith("h") else "input:narrative") for r in t["rows"]},
            "columns": {c["id"]: ("computed:row_number" if c["id"] == "r0" else "input:narrative") for c in t["columns"]}}


BINDING: dict[str, dict] = {
    "T3": {"rows": {**{k: "computed:iea_sector" for k in T3_SECTORS if k != "9"}, "9": "n/a"},
           "columns": {"a": "computed:label", "b": "computed:nace_crosswalk", "c": "computed:gross", "d": "computed:intensity",
                       "e": "computed:reference_year", "f": "computed:distance", "g": "input:cell"}},
    "T4": {"rows": {"1": "computed:top20"},
           "columns": {"a": "computed:gross", "b": "computed:share_of_book", "c": "input:ccm_sustainable",
                       "d": "input:residual_maturity_years(avg)", "e": "computed:count"}},
    "T10": {"rows": {str(i): "input:register" for i in range(1, 12)},
            "columns": {"a": "computed:label", "b": "computed:label", "c": "input:cell", "d": "input:cell",
                        "e": "input:cell", "f": "input:cell"}},
}


def tab_bindings(spec: dict) -> dict:
    """Tables 1-3: every printed row letter is authored; headings carry no value."""
    return {tid: _tab(spec, tid) for tid in ("TAB1", "TAB2", "TAB3")}


def qualitative_rows(spec: dict, tid: str) -> list[dict]:
    """The printed rows of a qualitative table with their group heading: [{key, row, group, prompt}]."""
    from services.regspec import template
    out, group = [], None
    table = {"TAB1": "table1", "TAB2": "table2", "TAB3": "table3"}[tid]
    for r in template(spec, tid)["rows"]:
        if r["id"].startswith("h"):
            group = r["label"]
            continue
        parts = re.findall(r"\(([^)]+)\)", r["id"]) or [r["id"]]      # '(d)(i)' → d, i
        out.append({"key": f"{table}.{'_'.join(parts)}", "row": r["id"], "group": group or "",
                    "prompt": r["label"].split(" > ")[-1]})
    return out


def template3_values(spec: dict, assets: list[dict], reference_year: int) -> dict:
    from services.governance import transition_alignment as TA
    by = {r["sector"]: r for r in TA.template3_grid(assets)["rows"]}
    codes: dict[str, list[str]] = {}
    for code, sec in TA._ANNEX_XL_NACE_CROSSWALK:
        codes.setdefault(sec, []).append(code)
    out = {}
    for rid, secs in T3_SECTORS.items():
        rows = [by[s] for s in secs if s in by]
        gross = sum(r["gross"] for r in rows) if rows else 0
        metric = "; ".join(f"{r['metric']}: {r['current_intensity']} {r['unit']}" for r in rows if r["current_intensity"] is not None)
        dist = [r["distance_pct"] for r in rows if r["distance_pct"] is not None]
        out[rid] = {"b": ", ".join(sorted({c for s in secs for c in codes.get(s, [])})) or None, "c": gross,
                    "d": metric or None, "e": reference_year if rows else None,
                    "f": (dist[0] if len(dist) == 1 else None) if dist else None, "g": None}
    return out


def template4_values(assets: list[dict]) -> dict:
    from services.governance import transition_alignment as TA
    from services.governance.pillar3_grids import gross_of
    t4 = TA.template4_top20(assets)
    matched = t4.get("assets") or []
    book = sum(gross_of(a) for a in assets)
    gross = sum(gross_of(a) for a in matched)
    ccm = [a for a in matched if a.get("ccm_sustainable") is not None]
    mat = [(gross_of(a), float(a["residual_maturity_years"])) for a in matched if a.get("residual_maturity_years") not in (None, "")]
    return {"1": {"a": gross, "b": round(100 * gross / book, 2) if book else None,
                  "c": sum(gross_of(a) for a in ccm if a["ccm_sustainable"]) if ccm else None,
                  "d": round(sum(g * m for g, m in mat) / sum(g for g, _ in mat), 1) if mat else None,
                  "e": t4["matched_count"]}}
