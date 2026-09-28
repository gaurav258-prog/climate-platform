"""SFDR principal-adverse-impacts statement (Delegated Regulation (EU) 2022/1288, Annex I): how every row and column of
Tables 1-3 is filled. The rows, their numbering and wording come from the spec file (data/reference/regspec/sfdr_pai);
nothing about the template is typed here. coverage() checks this map against every adopted spec.

Table 1   computed by the PAI engine from the holdings (indicator rows); the prior period, explanation and actions
          columns are completed by the filer on the form.
Tables 2, 3  opt-in: the filer adopts at least one indicator from each (Article 6(1)). Each investee-company row can be
          adopted; its per-issuer values are supplied by the client (issuer_voluntary_pai) and aggregated as the
          metric's wording requires:
            share          'Share of investments in …'  → % of invested value where the issuer's flag is true
            per_meur       '… per million EUR invested, expressed as a weighted average' → Σ (value / EVIC × issuer
                           amount) ÷ € million invested — the attribution of Annex I definition (3), as Table 1 no. 8-9
            avg            an issuer-level ratio, rate or count 'expressed as a weighted average' → average weighted by
                           the value invested (a ratio cannot be attributed; the spec's declared reading)
          Rows for sovereigns, real estate and green bonds, and rows whose metric is a breakdown or two figures, are
          not offered (n/a) — they need data this platform does not hold per issuer.
"""
from __future__ import annotations

_T1_COLS = {"a": "computed:indicator", "b": "computed:metric", "c": "computed:impact",
            "d": "input:prior_period", "e": "input:explanation", "f": "input:actions"}
_OPT_COLS = {"a": "computed:indicator", "b": "computed:impact_group", "c": "computed:metric"}


def _opt(rows: dict) -> dict:
    return {"rows": rows, "columns": dict(_OPT_COLS)}


BINDING: dict[str, dict] = {
    "T1": {
        "rows": {"1.1": "computed:indicator.1.scope_1", "1.2": "computed:indicator.1.scope_2",
                 "1.3": "computed:indicator.1.scope_3", "1.4": "computed:indicator.1.total",
                 **{str(n): f"computed:indicator.{n}" for n in range(2, 19)}},
        "columns": dict(_T1_COLS),
    },
    "T2": _opt({
        "1": "input:per_meur|t", "2": "input:per_meur|t", "3": "input:per_meur|t", "4": "input:share|%",
        "5": "n/a", "6.1": "input:avg|m³ per €M revenue", "6.2": "input:avg|%", "7": "input:share|%",
        "8": "input:share|%", "9": "input:share|%", "10": "input:share|%", "11": "input:share|%", "12": "input:share|%",
        "13": "input:per_meur|t", "14.1": "input:share|%", "14.2": "input:share|%", "15": "input:share|%",
        "16": "n/a", "17": "n/a", "18.1": "n/a", "18.2": "n/a", "18.3": "n/a", "18.4": "n/a", "19": "n/a", "20": "n/a",
        "21": "n/a", "22": "n/a"}),
    "T3": _opt({
        "1": "input:share|%", "2": "input:avg|rate", "3": "input:avg|workdays", "4": "input:share|%", "5": "input:share|%",
        "6": "input:share|%", "7.1": "input:avg|incidents", "7.2": "input:avg|incidents", "8": "input:avg|ratio",
        "9": "input:share|%", "10": "input:share|%", "11": "input:share|%", "12": "input:share|%", "13": "input:share|%",
        "14": "input:avg|cases", "15": "input:share|%", "16": "input:share|%", "17": "n/a",
        **{str(n): "n/a" for n in range(18, 25)}}),
}


def row_key(template_id: str, row_id: str) -> str:
    """The stored key of an opt-in indicator: its table and official row number ('T2', '6.1' → 't2_6_1')."""
    return f"{template_id.lower()}_{row_id.replace('.', '_')}"


def optional_catalog(spec: dict) -> dict[str, dict]:
    """Every adoptable Table 2 / Table 3 row of `spec`: key → table, kind, aggregation, unit, and the official wording."""
    from services.regspec import template
    out = {}
    for tid, kind in (("T2", "environmental"), ("T3", "social")):
        for r in template(spec, tid)["rows"]:
            how = BINDING[tid]["rows"].get(r["id"], "n/a")
            if how == "n/a":
                continue
            agg, _, unit = how.split(":", 1)[1].partition("|")
            parts = r["label"].split(" > ")
            out[row_key(tid, r["id"])] = {"table": int(tid[1]), "row": r["id"], "kind": kind, "agg": agg, "unit": unit,
                                          "name": _strip_number(parts[-2]) if len(parts) > 1 else parts[-1],
                                          "metric": _strip_number(parts[-1])}
    return out


def _strip_number(s: str) -> str:
    import re
    return re.sub(r"^\s*(\d+\.|[a-z]\))\s*", "", s).strip()
