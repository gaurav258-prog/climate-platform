"""Pillar 3 ESG Templates 1 and 5, built to the governing template specification (data/reference/regspec/bank_p3esg).

The rows and columns — ids, order and wording — come from the spec file of the version that governs the filing. This
module declares how each of them is filled (BINDING, checked for full coverage against every adopted spec) and fills
them from the book. Nothing about the template's structure is typed here.

Who is in which row (Annex XL):
  sector rows        exposures towards non-financial corporations, by the counterparty's NACE code (T1 point 3,
                     T5 column b). The counterparty's FINREP sector comes from the loan tape; where it is not stated it
                     is inferred from the NACE code and the asset type, and the form says how many were inferred.
  collateral rows    T5 rows 10-12: loans collateralised by residential / commercial immovable property and repossessed
                     collateral, whatever the counterparty (the spec's declared reading of T5 point 2). Stated on the
                     loan tape, else inferred from the asset type for residential and commercial property only.
Physical-risk sensitivity (T5 c-o) is an exposure with a High or Very high climate hazard at its location; chronic /
acute follow the institution's documented split (pillar3_templates). Columns the institution supplies (IFRS 9 stage,
impairment, Paris-benchmark exclusion, CCM, company-reported emissions) are summed over the exposures that state them;
a column no exposure states stays blank — never zero — and each template notes how many stated it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from services.governance.pillar3_templates import _asset_hits
from services.reference import nace as _nace

# How every row and column of Templates 1 and 5 is filled. Sources: computed (from the book and the engine), input (a
# per-loan fact the institution supplies), n/a. Row ids and column letters are the spec's; coverage() checks this map
# against every adopted spec, so a version that adds, drops or moves a row fails the build until it is mapped here.
BINDING: dict[str, dict] = {
    "T1": {
        "rows": {"1": "computed:subtotal", **{str(i): "computed:nace" for i in range(2, 53)},
                 "53": "computed:subtotal", "54": "computed:nace", "55": "computed:nace_in_label", "56": "computed:total"},
        "columns": {"a": "computed:gross", "b": "input:pab_excluded", "c": "input:ccm_sustainable",
                    "d": "input:ifrs9_stage=2", "e": "input:ifrs9_stage=3", "f": "input:accumulated_impairment_eur",
                    "g": "input:accumulated_impairment_eur|ifrs9_stage=2", "h": "input:accumulated_impairment_eur|ifrs9_stage=3",
                    # i-k: the institution's stated estimation and attribution (services.governance.pillar3_t1)
                    "i": "computed:ghg_financed", "j": "computed:ghg_financed_scope3", "k": "input:emissions_company_reported",
                    "l": "input:residual_maturity_years<=5", "m": "input:residual_maturity_years<=10",
                    "n": "input:residual_maturity_years<=20", "o": "input:residual_maturity_years>20",
                    "p": "input:residual_maturity_years(avg)"},
    },
    "T5": {
        "rows": {**{str(i): "computed:nace" for i in range(1, 10)},
                 "10": "computed:collateral:residential", "11": "computed:collateral:commercial",
                 "12": "computed:collateral:repossessed", "13": "computed:other_sections"},
        "columns": {"a": "computed:country", "b": "computed:gross",
                    "c": "input:residual_maturity_years<=5|sensitive", "d": "input:residual_maturity_years<=10|sensitive",
                    "e": "input:residual_maturity_years<=20|sensitive", "f": "input:residual_maturity_years>20|sensitive",
                    "g": "input:residual_maturity_years(avg)|sensitive",
                    "h": "computed:chronic_only", "i": "computed:acute_only", "j": "computed:chronic_and_acute",
                    "k": "input:ifrs9_stage=2|sensitive", "l": "input:ifrs9_stage=3|sensitive",
                    "m": "input:accumulated_impairment_eur|sensitive", "n": "input:accumulated_impairment_eur|sensitive,ifrs9_stage=2",
                    "o": "input:accumulated_impairment_eur|sensitive,ifrs9_stage=3"},
    },
}

# Which NACE sections a grouping row covers is read from the spec's own layout, never typed here:
#   subtotal         the section rows printed under it, up to the next subtotal or total row
#   nace_in_label    the sections its label names ('Exposures to other sectors (NACE codes J, M - U)')
#   other_sections   every section no NACE row of the template names ('Other relevant sectors')
#   total            every section any subtotal covers

# the asset types read as immovable-property collateral where the loan tape does not say — a declaration, in reference data
_COLLATERAL_BY_TYPE = json.loads((Path(__file__).resolve().parents[2] / "data" / "reference" / "declarations"
                                  / "immovable_collateral_by_asset_type.json").read_text())["by_asset_type"]
_NACE_ROW = re.compile(r"^([A-U])\.?(\d{2}(?:\.\d{1,2})?)?\s+-\s")
TOP_GEOGRAPHIES = 10


def gross_of(a: dict) -> float:
    """The gross carrying amount of an exposure: its outstanding balance, as the loan tape states it. Never the collateral
    value; an exposure without one sits in no row, and the Pillar 3 filing is blocked until it is stated
    (filing_validation: gross_carrying_amount_stated)."""
    return float(a.get("outstanding_loan_balance_eur") or 0)


def no_gross(assets: list[dict]) -> int:
    """How many exposures state no gross carrying amount."""
    return sum(1 for a in assets if not a.get("outstanding_loan_balance_eur"))


def counterparty(a: dict) -> tuple[str | None, bool]:
    """(FINREP sector, stated?) — as stated on the loan tape, else inferred: a NACE code in K is a financial corporation,
    in O with a government level a general government, any other NACE code a non-financial corporation; no NACE code on a
    residential property is a household."""
    s = (a.get("counterparty_sector") or "").strip().lower()
    if s:
        return s, True
    sec = _nace.section(a.get("nace_code"))
    if sec == "K":
        return "other_financial_corporation", False
    if sec == "O" and (a.get("counterparty_govt_level") or "").strip():
        return "general_government", False
    if sec:
        return "non_financial_corporation", False
    if a.get("asset_type") == "residential_real_estate":
        return "household", False
    return None, False


def collateral(a: dict) -> tuple[str | None, bool]:
    s = (a.get("immovable_collateral") or "").strip().lower()
    if s:
        return (None if s == "none" else s), True
    return _COLLATERAL_BY_TYPE.get(a.get("asset_type") or ""), False


def _nace_match(a: dict, section: str, dotted: str | None) -> bool:
    hit = _nace.lookup(a.get("nace_code"))
    if not hit or hit["section"] != section:
        return False
    if not dotted:
        return True
    d = hit["dotted"]
    return d == dotted or (d.startswith(dotted) and d[len(dotted)] in ".0123456789")


_SECTIONS = "ABCDEFGHIJKLMNOPQRSTU"


def _label_sections(label: str) -> set[str]:
    """'Exposures to other sectors (NACE codes J, M - U)' → {J, M, N, …, U}."""
    m = re.search(r"NACE codes?\s+([A-U](?:\s*(?:,|-|–)\s*[A-U])*)", label)
    if not m:
        return set()
    out: set[str] = set()
    for part in re.split(r"\s*,\s*", m.group(1)):
        ends = re.split(r"\s*[-–]\s*", part)
        a, b = ends[0], ends[-1]
        out |= set(_SECTIONS[_SECTIONS.index(a): _SECTIONS.index(b) + 1])
    return out


def _section_rows(template: dict) -> dict[str, set[str]]:
    """Row id → the NACE sections it covers, for every row bound to NACE: section rows, label-named groups, subtotals
    (the section-level rows printed under them) and the total — all read from the spec's rows and their order."""
    binding = BINDING[template["id"]]["rows"]
    own: dict[str, set[str]] = {}
    for r in template["rows"]:
        how = binding[r["id"]]
        m = _NACE_ROW.match(r["label"])
        if how == "computed:nace" and m and not m.group(2):
            own[r["id"]] = {m.group(1)}                             # a section row ('C - Manufacturing')
        elif how == "computed:nace_in_label":
            own[r["id"]] = _label_sections(r["label"])
    out = dict(own)
    current = None
    for r in template["rows"]:
        how = binding[r["id"]]
        if how in ("computed:subtotal", "computed:total"):
            current = r["id"] if how == "computed:subtotal" else None
            out.setdefault(r["id"], set())
        elif current and r["id"] in own:
            out[current] |= own[r["id"]]
    total = set().union(*(v for k, v in out.items() if binding[k] == "computed:subtotal"))
    for r in template["rows"]:
        if binding[r["id"]] == "computed:total":
            out[r["id"]] = total
        elif binding[r["id"]] == "computed:other_sections":
            named = set().union(*(v for k, v in own.items()))
            out[r["id"]] = set(_SECTIONS) - named
    return out


def _row_filter(template: dict, row: dict, how: str):
    """A predicate over (asset, counterparty sector, collateral kind) for one spec row."""
    kind, _, arg = how.partition(":")[2].partition(":")
    if kind in ("subtotal", "total", "nace_in_label", "other_sections"):
        secs = _section_rows(template)[row["id"]]
        if not secs:
            raise ValueError(f"{template['id']} row {row['id']}: the spec layout gives this {kind} row no NACE sections")
        return lambda a, cp, col: cp == "non_financial_corporation" and _nace.section(a.get("nace_code")) in secs
    if kind == "nace":
        m = _NACE_ROW.match(row["label"])
        if not m:
            raise ValueError(f"{template['id']} row {row['id']}: bound as a NACE row but its label names no NACE code")
        sec, dotted = m.group(1), m.group(2)
        return lambda a, cp, col: cp == "non_financial_corporation" and _nace_match(a, sec, dotted)
    if kind == "collateral":
        return lambda a, cp, col: col == arg
    raise ValueError(f"unknown row binding {how}")


def _maturity(a: dict):
    m = a.get("residual_maturity_years")
    if m not in (None, ""):
        try:
            return float(m)
        except (TypeError, ValueError):
            return None
    return 20.5 if a.get("no_stated_maturity") else None      # Annex XL: no stated maturity → the '> 20 years' bucket


def _stage(a: dict) -> str | None:
    s = str(a.get("ifrs9_stage") or "").lower().replace("stage", "").strip()
    return s or None


def _t1_financed(a: dict, x: float, t1: dict, g: dict, n: dict) -> None:
    """Columns i-k for one exposure on the institution's stated method (services.governance.pillar3_t1): its emissions
    of the scopes it estimates, attributed by the exposure compared to the counterparty's total liabilities."""
    from services.governance.pillar3_t1 import SCOPES, factor
    est = t1.get("estimation")
    if est not in SCOPES or not t1.get("attribution"):
        return
    vals = [a.get(k) for k in SCOPES[est]]
    s3 = a.get("ghg3") if est == "scope_1_2_3" else None
    if all(v in (None, "") for v in vals):
        return
    f = factor(a)
    if f is None:
        n["unattributed"] += 1                 # emissions stated, the counterparty's total liabilities not
        return
    if f > 1:
        n["over"] += 1                         # an exposure larger than everything the counterparty owes and owns
        return
    if all(v not in (None, "") for v in vals):
        n["ghg"] += 1
        g["ghg"] += f * sum(float(v) for v in vals)
        src = a.get("emissions_company_reported")
        if src is None:
            n["rep_unknown"] += 1              # the source of these emissions is not recorded: k cannot be read
        else:
            n["rep"] += 1
            g["rep"] += x if src else 0.0
    if s3 not in (None, ""):
        n["ghg3"] += 1
        g["ghg3"] += f * float(s3)


def _cells(assets: list[dict], template_id: str, level: float | None = None, t1: dict | None = None) -> tuple[dict, dict]:
    """Every column value for one row population, and how many exposures stated each supplied fact. Template 1 columns
    i-k follow the institution's stated method `t1` (a filing's frozen record); without one — a filing frozen before
    the statements were recorded — they are read as that filing printed them."""
    g = {k: 0.0 for k in ("gross", "sens", "le5", "m5_10", "m10_20", "gt20", "mx", "mg", "chronic_only", "acute_only",
                          "both", "s2", "npe", "imp", "imp_s2", "imp_npe", "pab", "ccm", "rep", "ghg", "ghg3")}
    n = {k: 0 for k in ("stage", "imp", "mat", "pab", "ccm", "rep", "all", "sens", "ghg", "ghg3", "unattributed", "over",
                        "rep_unknown")}
    for a in assets:
        x = gross_of(a)
        if not x:
            continue
        chronic, acute = _asset_hits(a, level) if template_id == "T5" else (False, False)
        sensitive = chronic or acute
        in_scope = sensitive if template_id == "T5" else True     # T5 c-o describe the sensitive exposures only
        g["gross"] += x
        n["all"] += 1
        if sensitive:
            n["sens"] += 1
            g["sens"] += x
            g["both" if chronic and acute else "chronic_only" if chronic else "acute_only"] += x
        if template_id == "T1" and t1 is not None:
            _t1_financed(a, x, t1, g, n)
            for key, fld in (("pab", "pab_excluded"), ("ccm", "ccm_sustainable")):
                if a.get(fld) is not None:
                    n[key] += 1
                    g[key] += x if a.get(fld) else 0.0
        elif template_id == "T1":
            # a filing frozen before the stated method (E103): the counterparties' reported emissions, not attributed —
            # only what an exposure states (E76); column i sums exposures stating all three scopes (E79)
            ghg = [a.get(k) for k in ("ghg1", "ghg2", "ghg3")]
            if all(v not in (None, "") for v in ghg):
                n["ghg"] += 1
                g["ghg"] += sum(float(v) for v in ghg if v not in (None, ""))
            if a.get("ghg3") not in (None, ""):
                n["ghg3"] += 1
                g["ghg3"] += float(a["ghg3"])
            for key, fld in (("pab", "pab_excluded"), ("ccm", "ccm_sustainable"), ("rep", "emissions_company_reported")):
                if a.get(fld) is not None:
                    n[key] += 1
                    g[key] += x if a.get(fld) else 0.0
        if not in_scope:
            continue
        m = _maturity(a)
        if m is not None:
            n["mat"] += 1
            g["le5" if m <= 5 else "m5_10" if m <= 10 else "m10_20" if m <= 20 else "gt20"] += x
            if a.get("residual_maturity_years") not in (None, ""):
                g["mx"] += x * m
                g["mg"] += x
        st = _stage(a)
        if st:
            n["stage"] += 1
            g["s2"] += x if st == "2" else 0.0
            g["npe"] += x if st == "3" else 0.0
        imp = a.get("accumulated_impairment_eur")
        if imp is not None:
            n["imp"] += 1
            v = abs(float(imp))
            g["imp"] += v
            g["imp_s2"] += v if st == "2" else 0.0
            g["imp_npe"] += v if st == "3" else 0.0
    return g, n


def _t1_ijk(g: dict, n: dict, t1: dict | None) -> dict:
    """Columns i, j, k. On the stated method: i the attributed emissions of the scopes estimated; j the attributed scope 3
    — blank where the institution states it does not yet estimate scope 3 (Annex XL, column j); k the share of the row's
    gross carrying amount (EBA Q&A 2024_7225: all its exposures) whose column-i emissions the counterparty reported — a
    gap where a column-i exposure does not record its emissions' source. All three blank when not stated (a named gap)
    or when the institution states it is not yet estimating."""
    from services.governance.pillar3_t1 import ESTIMATING, gaps
    if t1 is None:                                     # as a filing frozen before the stated method printed them
        return {"i": g["ghg"] if n["ghg"] else None, "j": g["ghg3"] if n["ghg3"] else None,
                "k": (round(g["rep"] / g["gross"] * 100, 1) if g["gross"] else None) if n["rep"] else None}
    if gaps(t1) or t1.get("estimation") not in ESTIMATING:
        return {"i": None, "j": None, "k": None}
    return {"i": g["ghg"] if n["ghg"] else None,
            "j": (g["ghg3"] if n["ghg3"] else None) if t1["estimation"] == "scope_1_2_3" else None,
            "k": None if n["rep_unknown"] or not g["gross"] else round(g["rep"] / g["gross"] * 100, 1)}


def _columns(g: dict, n: dict, template_id: str, t1: dict | None = None) -> dict:
    blank = lambda k, v: v if n[k] else None          # noqa: E731 — a fact no exposure states is blank, not zero
    avg = round(g["mx"] / g["mg"], 1) if g["mg"] else None
    if template_id == "T1":
        return {"a": g["gross"], "b": blank("pab", g["pab"]), "c": blank("ccm", g["ccm"]), "d": blank("stage", g["s2"]),
                "e": blank("stage", g["npe"]), "f": blank("imp", g["imp"]), "g": blank("imp", g["imp_s2"]),
                "h": blank("imp", g["imp_npe"]), **_t1_ijk(g, n, t1),
                "l": blank("mat", g["le5"]), "m": blank("mat", g["m5_10"]), "n": blank("mat", g["m10_20"]),
                "o": blank("mat", g["gt20"]), "p": avg}
    return {"b": g["gross"], "c": blank("mat", g["le5"]), "d": blank("mat", g["m5_10"]), "e": blank("mat", g["m10_20"]),
            "f": blank("mat", g["gt20"]), "g": avg, "h": g["chronic_only"], "i": g["acute_only"], "j": g["both"],
            "k": blank("stage", g["s2"]), "l": blank("stage", g["npe"]), "m": blank("imp", g["imp"]),
            "n": blank("imp", g["imp_s2"]), "o": blank("imp", g["imp_npe"]), "sensitive": g["sens"]}


def build(spec: dict, template_id: str, assets: list[dict], level: float | None = None, t1: dict | None = None) -> dict:
    """One template instance: every spec row with its column values, plus the population notes. Template 5 needs the
    institution's stated at-risk level (what makes an exposure sensitive); Template 1 columns i-k its stated estimation
    and attribution (`t1`, the filing's frozen pillar3_t1 record; None = a filing frozen before it was recorded)."""
    if template_id == "T5" and level is None:
        raise ValueError("Template 5 needs the stated at-risk level (method.at_risk_level)")
    from services.regspec import template as spec_template
    t = spec_template(spec, template_id)
    binding = BINDING[template_id]["rows"]
    tagged, inferred_cp, inferred_col, unallocated = [], 0, 0, 0
    for a in assets:
        if not gross_of(a):
            continue
        cp, cp_stated = counterparty(a)
        col, col_stated = collateral(a)
        inferred_cp += (not cp_stated and cp is not None)
        inferred_col += (not col_stated and col is not None)
        if cp == "non_financial_corporation" and _nace.section(a.get("nace_code")) is None:
            unallocated += 1
        tagged.append((a, cp, col))
    rows, shown = [], {}
    for r in t["rows"]:
        keep = _row_filter(t, r, binding[r["id"]])
        pop = [a for a, cp, col in tagged if keep(a, cp, col)]
        g, n = _cells(pop, template_id, level, t1)
        rows.append({"id": r["id"], "label": r["label"], "n": n["all"], "values": _columns(g, n, template_id, t1)})
        shown.update({id(a): a for a in pop})
    stated = _cells(list(shown.values()), template_id, level, t1)[1]  # each exposure once, however many rows it sits in
    return {"template": template_id, "rows": rows, "stated": stated, "inferred_counterparty": inferred_cp,
            "inferred_collateral": inferred_col, "unallocated_no_nace": unallocated, "no_gross_carrying_amount": no_gross(assets),
            **({"at_risk_level": level} if template_id == "T5" else {}),
            **({"t1_method": t1} if template_id == "T1" else {})}


def geographies(assets: list[dict]) -> list[tuple[str, str, list[dict]]]:
    """Template 5 column a: (code, label, exposures) for the countries with the largest exposure, then the rest
    together ('OTHER'), so no exposure leaves the geography axis."""
    by_c: dict[str, list] = {}
    for a in assets:
        if gross_of(a):
            by_c.setdefault((a.get("country") or "").strip().upper() or "?", []).append(a)
    ranked = sorted(by_c, key=lambda c: -sum(gross_of(a) for a in by_c[c]))
    top, rest = ranked[:TOP_GEOGRAPHIES], ranked[TOP_GEOGRAPHIES:]
    out = [(c, "Geography not stated" if c == "?" else c, by_c[c]) for c in top]
    if rest:
        out.append(("OTHER", "Other countries (" + ", ".join(rest[:8]) + ("…" if len(rest) > 8 else "") + ")",
                    [a for c in rest for a in by_c[c]]))
    return out


def template5(spec: dict, assets: list[dict], level: float) -> dict:
    """Template 5 for the whole book and per geography (column a)."""
    whole = build(spec, "T5", assets, level)
    geos = [{"geography": c, "label": label, **build(spec, "T5", pop, level)} for c, label, pop in geographies(assets)]
    return {**whole, "geographies": geos}


def row_population(spec: dict, template_id: str, row_id: str, assets: list[dict]) -> list[dict]:
    """The exposures one template row holds — the same tagging and row filter build() uses."""
    from services.regspec import template as spec_template
    t = spec_template(spec, template_id)
    r = next((x for x in t["rows"] if x["id"] == row_id), None)
    if r is None:
        raise ValueError(f"{template_id} has no row {row_id}")
    keep = _row_filter(t, r, BINDING[template_id]["rows"][r["id"]])
    return [a for a in assets if gross_of(a) and keep(a, counterparty(a)[0], collateral(a)[0])]


def t5_contribution(a: dict, col: str, level: float) -> dict | None:
    """What one exposure adds to a Template 5 cell (column b-o) — None when it is not in the cell. {'amount'} for a sum
    column; {'weight', 'maturity'} for column g (the gross-weighted average maturity). Mirrors _cells/_columns; a test
    rebuilds every cell from these and requires it to equal the grid."""
    x = gross_of(a)
    if not x:
        return None
    if col == "b":
        return {"amount": x}
    chronic, acute = _asset_hits(a, level)
    if not (chronic or acute):
        return None
    if col in ("h", "i", "j"):
        hit = {"h": chronic and not acute, "i": acute and not chronic, "j": chronic and acute}[col]
        return {"amount": x} if hit else None
    if col in ("c", "d", "e", "f"):
        m = _maturity(a)
        if m is None:
            return None
        bucket = "c" if m <= 5 else "d" if m <= 10 else "e" if m <= 20 else "f"
        return {"amount": x} if bucket == col else None
    if col == "g":
        m = a.get("residual_maturity_years")
        return None if m in (None, "") or _maturity(a) is None else {"weight": x, "maturity": float(m)}
    st = _stage(a)
    if col in ("k", "l"):
        return {"amount": x} if st == {"k": "2", "l": "3"}[col] else None
    if col in ("m", "n", "o"):
        imp = a.get("accumulated_impairment_eur")
        if imp is None or (col == "n" and st != "2") or (col == "o" and st != "3"):
            return None
        return {"amount": abs(float(imp))}
    raise ValueError(f"Template 5 column {col} is not a sum over exposures")
