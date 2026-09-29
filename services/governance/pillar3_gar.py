"""Pillar 3 Templates 2, 6, 7, 8, 9.1, 9.2 and 9.3, built to the governing template specification.

Rows, columns and their wording come from the spec file. This module declares, per spec row, WHICH exposures it holds
(a filter over the exposure's stated facts) or which rows it adds up, and per column WHAT is measured; coverage() checks
the map against every adopted spec. A cell whose fact no exposure in the row states is blank, never zero.

Facts per exposure (loan tape / attributes upload; see bank_gar_facts migration): FINREP counterparty sector and
sub-sector, instrument type, NFRD subject, loan purpose, immovable collateral, government level, trading book, EU or
not (Eurostat GISCO membership), Taxonomy status / objective / contribution type, specialised lending, EP score, EPC.
Declared defaults (reference data, counted on the form): an unstated instrument is a loan (the tape records loans);
counterparty sector and collateral are inferred as in pillar3_grids.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from services.governance.pillar3_grids import collateral, counterparty, gross_of
from services.reference.eu_membership import is_member as eu_member

_DECL = Path(__file__).resolve().parents[2] / "data" / "reference" / "declarations"
_INSTRUMENT_DEFAULT = json.loads((_DECL / "instrument_type_default.json").read_text())["default"]
_GAR_INSTRUMENTS = ("loans_and_advances", "debt_securities", "equity_instruments")
_FIN = ("credit_institution", "other_financial_corporation")


def _i(**kw) -> dict:
    return kw


def _sum(*ids: str) -> dict:
    return {"sum": list(ids)}


_L, _D, _E = "loans_and_advances", "debt_securities", "equity_instruments"


def _by_instrument(base: dict, first: int) -> dict:
    """The three instrument rows printed under a counterparty row: loans, debt securities, equity."""
    return {str(first): {**base, "instr": _L}, str(first + 1): {**base, "instr": _D}, str(first + 2): {**base, "instr": _E}}


_CI = _i(cp="credit_institution", gar=True)
_IF = _i(cp="other_financial_corporation", sub="investment_firm", gar=True)
_MC = _i(cp="other_financial_corporation", sub="management_company", gar=True)
_IU = _i(cp="other_financial_corporation", sub="insurance_undertaking", gar=True)
_NFRD = _i(cp="non_financial_corporation", nfrd=True, gar=True)
_EU_SME = _i(cp="non_financial_corporation", nfrd=False, eu=True, gar=True)
_NONEU = _i(cp="non_financial_corporation", nfrd=False, eu=False, gar=True)
_HH = _i(cp="household", gar=True)
_LG = _i(cp="general_government", govt=("local", "regional"), gar=True)

# Template 7 — assets for the calculation of the GAR. Rows under h2 / h3 carry the gross carrying amount only (col a).
T7_ROWS: dict[str, dict] = {
    "h1": {"heading": True}, "1": _sum("2", "20", "24", "28", "31"), "2": _sum("3", "7"), "3": _CI,
    **_by_instrument(_CI, 4), "7": _sum("8", "12", "16"), "8": _IF, **_by_instrument(_IF, 9), "12": _MC,
    **_by_instrument(_MC, 13), "16": _IU, **_by_instrument(_IU, 17), "20": _NFRD, **_by_instrument(_NFRD, 21),
    "24": _HH, "25": {**_HH, "col": "residential"}, "26": {**_HH, "purpose": "building_renovation"},
    "27": {**_HH, "purpose": "motor_vehicle"}, "28": _LG, "29": {**_LG, "purpose": "housing"},
    "30": {**_LG, "purpose_not": "housing"}, "31": _i(col="repossessed", trading=False), "32": _sum("1"),
    "h2": {"heading": True}, "33": _EU_SME, **_by_instrument(_EU_SME, 34), "37": _NONEU, **_by_instrument(_NONEU, 38),
    "41": _i(instr="derivatives", trading=False), "42": _i(instr="on_demand_interbank", trading=False),
    "43": _i(instr="cash", trading=False), "44": _i(instr="other_assets", trading=False),
    "45": _sum("32", "33", "37", "41", "42", "43", "44"),
    "h3": {"heading": True}, "46": _i(cp="general_government", govt=("central",), trading=False),
    "47": _i(cp="central_bank", trading=False), "48": _i(trading=True), "49": _sum("46", "47", "48"), "50": {"all": True},
}
T7_GROSS_ONLY_FROM = "h2"                      # from this heading on, only the gross carrying amount applies

# Template 9.1 — BTAR assets: the GAR assets (Template 7 row 32) plus non-NFRD corporates
T91_ROWS: dict[str, dict] = {
    "1": {"t7": "32"}, "h1": {"heading": True}, "2": _EU_SME, "3": {**_EU_SME, "instr": _L},
    "4": {**_EU_SME, "instr": _L, "col": "commercial"}, "5": {**_EU_SME, "instr": _L, "purpose": "building_renovation"},
    "6": {**_EU_SME, "instr": _D}, "7": {**_EU_SME, "instr": _E}, "8": _NONEU, **_by_instrument(_NONEU, 9),
    "12": _sum("1", "2", "8"), "h2": {"heading": True}, "13": {"t7": "41"}, "14": {"t7": "42"}, "15": {"t7": "43"},
    "16": {"t7": "44"}, "17": _sum("12", "13", "14", "15", "16"), "h3": {"heading": True}, "18": {"t7": "49"},
    "19": {"t7": "50"},
}
T91_GROSS_ONLY_FROM = "h2"

# Template 7 / 9.1 columns: (objective, measure). Objective None = TOTAL (CCM + CCA), read from the Taxonomy status alone.
_COLS_ASSETS = {
    "a": (None, "gross"), "b": ("ccm", "eligible"), "c": ("ccm", "aligned"), "d": ("ccm", "specialised"),
    "e": ("ccm", "transitional"), "f": ("ccm", "enabling"), "g": ("cca", "eligible"), "h": ("cca", "aligned"),
    "i": ("cca", "specialised"), "j": ("cca", "adaptation"), "k": ("cca", "enabling"), "l": ("all", "eligible"),
    "m": ("all", "aligned"), "n": ("all", "specialised"), "o": ("all", "transitional_or_adaptation"), "p": ("all", "enabling"),
}
# Template 8 / 9.2 ratio columns → the Template 7 / 9.1 numerator column; p / af are the coverage columns
_RATIO_NUM = dict(zip("abcdefghijklmno", "bcdefghijklmnop"))
_RATIO_NUM.update(dict(zip(["q", "r", "s", "t", "u", "v", "w", "x", "y", "z", "aa", "ab", "ac", "ad", "ae"], "bcdefghijklmnop")))
_FLOW_COLS = {"q", "r", "s", "t", "u", "v", "w", "x", "y", "z", "aa", "ab", "ac", "ad", "ae", "af"}
# Template 8 row → Template 7 row it expresses as a ratio (row 1 GAR = the GAR assets, Template 7 row 32)
T8_FROM_T7 = {"1": "32", "2": "1", "3": "2", "4": "3", "5": "7", "6": "8", "7": "12", "8": "16", "9": "20", "10": "24",
              "11": "25", "12": "26", "13": "27", "14": "28", "15": "29", "16": "30", "17": "31"}
T92_FROM_T91 = {"1": "12", "2": "1", "3": "2", "4": "4", "5": "5", "6": "8"}

# Template 2 — loans collateralised by immovable property: EU / non-EU area, by collateral type
def _t2_area(first: int, eu: bool) -> dict:
    """Rows printed per area: all collateralised loans, commercial, residential, repossessed, EP score estimated."""
    b = {"eu": eu}
    return {str(first): {**b, "col_any": True}, str(first + 1): {**b, "col": "commercial"},
            str(first + 2): {**b, "col": "residential"}, str(first + 3): {**b, "col": "repossessed"},
            str(first + 4): {**b, "col_any": True, "ep_estimated": True}}


T2_ROWS: dict[str, dict] = {**_t2_area(1, True), **_t2_area(6, False)}
_EP_BUCKETS = {"b": (0, 100), "c": (100, 200), "d": (200, 300), "e": (300, 400), "f": (400, 500), "g": (500, None)}
_EPC = dict(zip("hijklmn", "ABCDEFG"))

BINDING: dict[str, dict] = {
    "T2": {"rows": {k: "computed:filter" for k in T2_ROWS},
           "columns": {"a": "computed:gross", **{c: "input:ep_score_kwh_m2" for c in _EP_BUCKETS},
                       **{c: "input:epc_label" for c in _EPC}, "o": "input:epc_label=none", "p": "input:ep_score_estimated"}},
    "T7": {"rows": {k: ("n/a" if v.get("heading") else "computed:sum" if "sum" in v else "computed:filter") for k, v in T7_ROWS.items()},
           "columns": {c: ("computed:gross" if m == "gross" else f"input:taxonomy_{m}") for c, (o, m) in _COLS_ASSETS.items()}},
    "T9_1": {"rows": {k: ("n/a" if v.get("heading") else "computed:sum" if "sum" in v else "computed:filter") for k, v in T91_ROWS.items()},
             "columns": {c: ("computed:gross" if m == "gross" else f"input:taxonomy_{m}") for c, (o, m) in _COLS_ASSETS.items()}},
    "T8": {"rows": {k: f"computed:ratio:T7.{v}" for k, v in T8_FROM_T7.items()},
           "columns": {**{c: "computed:ratio" for c in _RATIO_NUM}, "p": "computed:coverage", "af": "computed:coverage_flow"}},
    "T9_2": {"rows": {k: f"computed:ratio:T9_1.{v}" for k, v in T92_FROM_T91.items()},
             "columns": {**{c: "computed:ratio" for c in _RATIO_NUM}, "p": "computed:coverage", "af": "computed:coverage_flow"}},
    "T6": {"rows": {"r1": "computed:T8.1.stock", "r2": "computed:T8.1.flow"},
           "columns": {"c1": "computed:ccm", "c2": "computed:cca", "c3": "computed:total", "c4": "computed:coverage"}},
    "T9_3": {"rows": {"r1": "computed:T9_2.1.stock", "r2": "computed:T9_2.1.flow"},
             "columns": {"c1": "computed:ccm", "c2": "computed:cca", "c3": "computed:total", "c4": "computed:coverage"}},
}


# ───────────────────────────── facts and filters ─────────────────────────────

def facts(a: dict, period: tuple[date, date] | None = None) -> dict:
    cp, _ = counterparty(a)
    col, _ = collateral(a)
    instr = (a.get("instrument_type") or "").strip().lower() or None
    status = (a.get("taxonomy_status") or "").strip().lower()
    orig = str(a.get("loan_origination_date") or "")[:10]
    return {"cp": cp, "sub": a.get("counterparty_subsector"), "instr": instr or _INSTRUMENT_DEFAULT,
            "instr_stated": instr is not None, "nfrd": a.get("nfrd_subject"), "purpose": a.get("loan_purpose"),
            "col": col, "govt": (a.get("counterparty_govt_level") or "").strip().lower() or None,
            "trading": bool(a.get("trading_book")), "eu": eu_member(a.get("country")),
            "assessed": status in ("eligible", "aligned", "not_eligible"), "eligible": status in ("eligible", "aligned"),
            # alignment is known only where it is stated: an 'aligned' status or the client's CCM-sustainable fact. The
            # Taxonomy classifier establishes eligibility only (it never returns 'aligned'), so 'eligible' ≠ 'not aligned'.
            "aligned": status == "aligned" or a.get("ccm_sustainable") is True,
            "aligned_known": status in ("aligned", "not_eligible") or a.get("ccm_sustainable") is not None,
            "objective": a.get("taxonomy_objective"),
            "contribution": a.get("taxonomy_contribution"), "specialised": a.get("specialised_lending"),
            "new": bool(period and orig and period[0].isoformat() <= orig <= period[1].isoformat()),
            "ep": a.get("ep_score_kwh_m2"), "ep_estimated": a.get("ep_score_estimated"),
            "epc": (str(a.get("epc_label") or "").strip().upper() or None)}


def _in_bucket(e: float, bounds: tuple) -> bool:
    lo, hi = bounds
    return (e >= lo if lo == 0 else e > lo) and (hi is None or e <= hi)


def _keep(f: dict, rule: dict) -> bool:
    for k, v in rule.items():
        if k in ("heading", "sum", "t7", "all"):
            continue
        if k == "gar":
            if f["trading"] or f["instr"] not in _GAR_INSTRUMENTS:
                return False
        elif k == "govt":
            if f["govt"] not in v:
                return False
        elif k == "purpose_not":
            if f["purpose"] == v:
                return False
        elif k == "col_any":
            if f["col"] not in ("commercial", "residential", "repossessed"):
                return False
        elif f.get(k) != v:
            return False
    return True


# ───────────────────────────── measures ─────────────────────────────

def _measure(pop: list[tuple[dict, float]], objective, measure) -> float | None:
    """The amount for one Template 7 / 9.1 column over a row's exposures; None when no exposure states the fact."""
    if measure == "gross":
        return sum(x for _, x in pop)
    if objective in ("ccm", "cca"):
        # known for this objective: an exposure that states its objective, or one assessed as not eligible (zero for any)
        known = [f for f, _ in pop if f["objective"] or (f["assessed"] and not f["eligible"])]
        pop = [(f, x) for f, x in pop if f["objective"] == objective]
    else:
        known = [f for f, _ in pop if f["assessed"]]
    if not known:
        return None
    if measure == "eligible":
        return sum(x for f, x in pop if f["eligible"])
    if not any(f["aligned_known"] for f, _ in pop) and not any(f["aligned_known"] for f in known):
        return None                                           # no exposure here has its alignment established
    aligned = [(f, x) for f, x in pop if f["aligned"]]
    if measure == "aligned":
        return sum(x for _, x in aligned)
    if measure == "specialised":
        return sum(x for f, x in aligned if f["specialised"]) if any(f["specialised"] is not None for f, _ in aligned) else None
    want = {"transitional": ("transitional",), "enabling": ("enabling",), "adaptation": ("adaptation",),
            "transitional_or_adaptation": ("transitional", "adaptation")}[measure]
    if not any(f["contribution"] for f, _ in aligned):
        return None
    return sum(x for f, x in aligned if f["contribution"] in want)


def _assets_grid(spec: dict, tid: str, rows_rule: dict, gross_only_from: str, tagged, t7_values=None) -> dict:
    from services.regspec import template
    t = template(spec, tid)
    values: dict[str, dict] = {}
    gross_only = False
    for r in t["rows"]:
        rule = rows_rule[r["id"]]
        if r["id"] == gross_only_from:
            gross_only = True
        if rule.get("heading"):
            continue
        if "t7" in rule:
            values[r["id"]] = dict((t7_values or {}).get(rule["t7"]) or {})
            continue
        if "sum" in rule:
            continue
        pop = [(f, x) for f, x in tagged if _keep(f, rule)]
        values[r["id"]] = {c: (_measure(pop, o, m) if (m == "gross" or not gross_only) else None)
                           for c, (o, m) in _COLS_ASSETS.items()}
        values[r["id"]]["_n"] = len(pop)
        values[r["id"]]["_gross_only"] = gross_only
    order = [r["id"] for r in t["rows"]]
    gross_only_rows = set(order[order.index(gross_only_from):]) if gross_only_from in order else set()

    def total(rid: str, seen: tuple = ()) -> dict:
        """A total row: the sum of the rows it names, each resolved first (a total may name a total printed below it)."""
        if rid in seen:
            raise ValueError(f"{tid}: row {rid} totals itself")
        if rid in values:
            return values[rid]
        parts = [total(i, seen + (rid,)) for i in rows_rule[rid]["sum"]]
        values[rid] = {c: (sum(p[c] for p in parts if p.get(c) is not None)
                           if any(p.get(c) is not None for p in parts) and (c == "a" or rid not in gross_only_rows) else None)
                       for c in _COLS_ASSETS}
        values[rid]["_gross_only"] = rid in gross_only_rows
        return values[rid]
    for r in t["rows"]:
        if "sum" in rows_rule[r["id"]]:
            total(r["id"])
    return values


def _ratios(assets_values: dict, row_map: dict, denom_row: str, total_row: str, flows: dict | None) -> dict:
    """Template 8 / 9.2: each ratio = the Template 7 / 9.1 amount ÷ the covered assets (the denominator row), in %."""
    def pct(n, d):
        return round(100 * n / d, 2) if n is not None and d else None
    den = (assets_values.get(denom_row) or {}).get("a")
    fden = ((flows or {}).get(denom_row) or {}).get("a")
    out = {}
    for rid, src in row_map.items():
        v, fv = assets_values.get(src) or {}, (flows or {}).get(src) or {}
        row = {}
        for col, num in _RATIO_NUM.items():
            row[col] = pct(fv.get(num), fden) if col in _FLOW_COLS else pct(v.get(num), den)
        out[rid] = row
    tot, ftot = (assets_values.get(total_row) or {}).get("a"), ((flows or {}).get(total_row) or {}).get("a")
    first = next(iter(row_map))
    out[first]["p"] = pct(den, tot)
    out[first]["af"] = pct(fden, ftot)
    return out


# ───────────────────────────── the templates ─────────────────────────────

def build(spec: dict, assets: list[dict], period_end: date | None = None) -> dict:
    """Every GAR / BTAR / EPC template the spec carries, keyed by template id → {row_id: {col: value}}, plus counts."""
    pe = period_end or date(date.today().year - 1, 12, 31)
    period = (date(pe.year, 1, 1), pe)
    tagged = [(facts(a, period), gross_of(a)) for a in assets if gross_of(a)]
    new = [(f, x) for f, x in tagged if f["new"]]
    t7 = _assets_grid(spec, "T7", T7_ROWS, T7_GROSS_ONLY_FROM, tagged)
    t7_new = _assets_grid(spec, "T7", T7_ROWS, T7_GROSS_ONLY_FROM, new)
    t91 = _assets_grid(spec, "T9_1", T91_ROWS, T91_GROSS_ONLY_FROM, tagged, t7)
    t91_new = _assets_grid(spec, "T9_1", T91_ROWS, T91_GROSS_ONLY_FROM, new, t7_new)
    t8 = _ratios(t7, T8_FROM_T7, "45", "50", t7_new)
    t92 = _ratios(t91, T92_FROM_T91, "17", "19", t91_new)

    def summary(r):                                        # Template 6 / 9.3 from the first ratio row (Annex XL, T6 para 3-4)
        return {"r1": {"c1": r.get("b"), "c2": r.get("g"), "c3": r.get("l"), "c4": r.get("p")},
                "r2": {"c1": r.get("r"), "c2": r.get("w"), "c3": r.get("ab"), "c4": r.get("af")}}
    t2 = {}
    for rid, rule in T2_ROWS.items():
        pop = [(f, x) for f, x in tagged if _keep(f, rule)]
        ep_known = [(f, x) for f, x in pop if f["ep"] is not None]
        epc_known = [(f, x) for f, x in pop if f["epc"] in _EPC.values()]
        row = {"a": sum(x for _, x in pop)}
        for c, bounds in _EP_BUCKETS.items():               # '0; <= 100', '> 100; <= 200', … '> 500'
            row[c] = sum(x for f, x in ep_known if _in_bucket(float(f["ep"]), bounds)) if ep_known else None
        for c, lbl in _EPC.items():
            row[c] = sum(x for f, x in epc_known if f["epc"] == lbl) if epc_known else None
        row["o"] = sum(x for f, x in pop if f["epc"] not in _EPC.values())
        row["p"] = (sum(x for f, x in pop if f["ep_estimated"]) if any(f["ep_estimated"] is not None for f, _ in pop) else None)
        row["_n"] = len(pop)
        t2[rid] = row
    counts = {"exposures": len(tagged), "new_in_period": len(new),
              "instrument_assumed": sum(1 for f, _ in tagged if not f["instr_stated"]),
              "objective_stated": sum(1 for f, _ in tagged if f["objective"]),
              "eligible_alignment_unknown": sum(1 for f, _ in tagged if f["eligible"] and not f["aligned_known"]),
              "nfc_nfrd_unstated": sum(1 for f, _ in tagged if f["cp"] == "non_financial_corporation" and f["nfrd"] is None),
              "unclassified_gross": ((t7.get("50") or {}).get("a") or 0) - ((t7.get("45") or {}).get("a") or 0)
                                    - ((t7.get("49") or {}).get("a") or 0),
              "period": [period[0].isoformat(), period[1].isoformat()]}
    return {"T2": t2, "T7": t7, "T8": t8, "T6": summary(t8.get("1") or {}), "T9_1": t91, "T9_2": t92,
            "T9_3": summary(t92.get("1") or {}), "counts": counts}
