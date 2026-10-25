"""PCAF mortgages — Part A: Financed Emissions, Third Edition (December 2025), §5.5. The pinned file and each rule with its
section, table and page: data/reference/pcaf/part_a_2025.json (PCAF's text is copyrighted; the file states the rules in
our words and points to the page).

Per mortgage b — a loan the bank states is in PCAF's asset class 'mortgages' (it cannot be read from the counterparty's
sector: a household's home equity loan or renovation loan is not one, and a company's mortgage is, §5.5 pp. 83 and 87):

  attribution factor_b = outstanding amount_b / property value at origination_b                           (§5.5 p. 84)
      the value at origination where stated; else the latest value the bank fixed instead, where the value at
      origination cannot be obtained (kept for the following years: services.ingest.sector_ingest refuses a changed
      one); else a named gap. §5.5 states no cap: a factor above 1 is computed as written and counted.
  building emissions_b = Σ_e energy_b,e × emission factor_e                                              (§5.5 p. 84)
      the energy figure by its basis (Table 5.5-1, Table 10.1-5): metered — the year's kWh; energy label or statistics
      per m² — kWh/m² × the loan's floor area; statistics per building — kWh per building × the number of buildings.
      Scope 1: fuel burned in the building; scope 2: purchased electricity, heating or cooling (glossary, p. 181).
  financed emissions_b = attribution factor_b × building emissions_b, scopes 1 and 2 (those §5.5 covers, p. 83)
  data quality score_b = the score of the one Table 5.5-1 option all the building's energy rows use. A building read by
      more than one option, or by an estimate with the supplier's own factor, has no score in the table: its emissions
      are still computed (each term a stated figure) and its score is named as not defined, with the reason.

Every missing input is a named gap (messages pcaf.mortgage.gap.*), listed in the order the formula needs them; the book
counts each mortgage under its first.

The book (§6.1 pp. 161-168, Table 10.2-2 p. 199): scope 1, scope 2 and scope 1+2 over the mortgages with a figure, the
outstanding amount they cover and its share of the mortgages', the data quality score weighted by outstanding amount
over the mortgages with a score (Σ outstanding × score / Σ outstanding), and the mortgages without a figure by reason.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "pcaf" / "part_a_2025.json"
MORTGAGES = "mortgages"
GAPS = ("no_outstanding", "no_property_value", "label_without_energy", "no_energy", "no_floor_area", "no_emission_factor")
KG_PER_T = 1000.0


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def method_of(asset_class: Optional[str]) -> Optional[str]:
    """The attribution the platform computes for a PCAF asset class: 'evic', 'mortgage', or None (not built)."""
    return {c["key"]: c["method"] for c in reference()["asset_classes"]}.get(asset_class)


def evic_classes() -> frozenset[str]:
    """The asset classes attributed by the counterparty's enterprise value (where EVIC is the denominator, E322)."""
    return frozenset(c["key"] for c in reference()["asset_classes"] if c["method"] == "evic")


def _options() -> dict[tuple[str, str], dict]:
    return {(o["energy_basis"], o["factor_type"]): o for o in reference()["mortgages"]["data_quality"]["options"]}


def _scope() -> dict[str, int]:
    return reference()["mortgages"]["energy_sources"]["scope"]


def _num(v) -> Optional[float]:
    return None if v is None or v == "" else float(v)


def attribution(a: dict) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """(factor, which value it divides by — 'at_origination' | 'latest_fixed', the gap) for one mortgage."""
    out = _num(a.get("outstanding_loan_balance_eur"))
    if out is None:
        return None, None, "no_outstanding"
    v0, vf = _num(a.get("property_value_at_origination_eur")), _num(a.get("property_value_fixed_eur"))
    if v0 is not None and v0 > 0:
        return out / v0, "at_origination", None
    if vf is not None and vf > 0:
        return out / vf, "latest_fixed", None
    return None, None, "no_property_value"


def _energy_kwh(r: dict, floor_area: Optional[float]) -> tuple[Optional[float], Optional[str]]:
    """One energy row's kWh for the year, or the gap that stops it."""
    basis = r.get("energy_basis")
    spec = reference()["mortgages"]["energy_bases"].get(basis)
    if spec is None:
        return None, "no_energy"
    value = _num(r.get(spec["value"]))
    if value is None:
        return None, "no_energy"
    times = spec.get("times")
    if times == "floor_area_m2":
        return (value * floor_area, None) if floor_area is not None and floor_area > 0 else (None, "no_floor_area")
    if times == "buildings":
        n = _num(r.get("buildings"))
        return (value * n, None) if n is not None and n >= 1 else (None, "no_energy")
    return value, None


def building(a: dict) -> dict:
    """The building's scope 1 and 2 emissions (t CO₂e) from its energy rows, its data quality option and the gaps."""
    rows = a.get("building_energy") or []
    if not rows:
        return {"gaps": ["label_without_energy" if a.get("epc_label") else "no_energy"]}
    years = [r.get("energy_year") for r in rows if r.get("energy_year") is not None]
    if years:                                    # one year's use: the most recent year stated (§6.1, most recent data)
        rows = [r for r in rows if r.get("energy_year") == max(years)]
    floor, scope = _num(a.get("floor_area_m2")), _scope()
    s1 = s2 = 0.0
    gaps: list[str] = []
    for r in rows:
        kwh, gap = _energy_kwh(r, floor)
        ef = _num(r.get("emission_factor_kg_per_kwh"))
        missing = [g for g in (gap, None if ef is not None else "no_emission_factor") if g]
        if missing:
            gaps += missing
            continue
        t = kwh * ef / KG_PER_T
        if scope.get(r.get("energy_source")) == 1:
            s1 += t
        else:
            s2 += t
    gaps = sorted(set(gaps), key=GAPS.index)
    if gaps:
        return {"gaps": gaps}
    opts = {(r.get("energy_basis"), r.get("emission_factor_type")) for r in rows}
    known = _options()
    if len(opts) > 1:
        option, score, score_gap = None, None, "mixed"
    elif next(iter(opts)) not in known:
        option, score, score_gap = None, None, "no_option"
    else:
        o = known[next(iter(opts))]
        option, score, score_gap = o["option"], o["score"], None
    return {"scope1": s1, "scope2": s2, "option": option, "score": score, "score_gap": score_gap, "gaps": []}


def loan(a: dict) -> dict:
    """One mortgage's PCAF figure: its attribution, its building's and its financed scope 1 and 2 emissions (t CO₂e),
    its data quality score — or every gap, in the order the formula needs the inputs (the first is its reason)."""
    af, basis, att_gap = attribution(a)
    b = building(a)
    gaps = ([att_gap] if att_gap else []) + b["gaps"]
    out: dict = {"attribution_factor": None if af is None else round(af, 6), "property_value_basis": basis,
                 "gaps": sorted(gaps, key=GAPS.index)}
    if b["gaps"]:
        return out
    out.update({"building_scope1_tco2e": round(b["scope1"], 4), "building_scope2_tco2e": round(b["scope2"], 4),
                "dq_option": b["option"], "dq_score": b["score"], "dq_gap": b["score_gap"]})
    if af is not None:
        out.update({"financed_scope1_tco2e": round(af * b["scope1"], 4), "financed_scope2_tco2e": round(af * b["scope2"], 4),
                    "financed_tco2e": round(af * (b["scope1"] + b["scope2"]), 4)})
    return out


def is_mortgage(a: dict) -> bool:
    return a.get("pcaf_asset_class") == MORTGAGES


def book(assets: list[dict]) -> dict:
    """The mortgages of a book (the loans stated in PCAF's 'mortgages' class), as Table 10.2-2 reports an asset class.
    Sets each asset's own figure on it ('pcaf_mortgage') for the screens that drill into the book."""
    rows = [a for a in assets if is_mortgage(a)]
    s1 = s2 = 0.0
    n_with = n_scored = n_above = 0
    outstanding = covered = scored_out = scored_x = 0.0
    by_score: dict[int, dict] = {}
    gaps: dict[str, dict] = {}
    no_score: dict[str, int] = {}
    basis = {"at_origination": 0, "latest_fixed": 0}
    for a in rows:
        r = loan(a)
        a["pcaf_mortgage"] = r
        out = _num(a.get("outstanding_loan_balance_eur")) or 0.0
        outstanding += out
        if r["property_value_basis"]:
            basis[r["property_value_basis"]] += 1
        if r["attribution_factor"] is not None and r["attribution_factor"] > 1:
            n_above += 1
        if r["gaps"]:
            g = gaps.setdefault(r["gaps"][0], {"n": 0, "outstanding_eur": 0.0})
            g["n"] += 1
            g["outstanding_eur"] += out
            continue
        n_with += 1
        covered += out
        s1 += r["financed_scope1_tco2e"]
        s2 += r["financed_scope2_tco2e"]
        if r["dq_score"] is None:
            no_score[r["dq_gap"]] = no_score.get(r["dq_gap"], 0) + 1
            continue
        n_scored += 1
        scored_out += out
        scored_x += out * r["dq_score"]
        sc = by_score.setdefault(r["dq_score"], {"n": 0, "outstanding_eur": 0.0, "financed_tco2e": 0.0})
        sc["n"] += 1
        sc["outstanding_eur"] += out
        sc["financed_tco2e"] += r["financed_tco2e"]
    has = n_with > 0
    return {
        "n_loans": len(rows), "outstanding_eur": round(outstanding),
        "n_with_emissions": n_with, "covered_outstanding_eur": round(covered),
        "coverage_pct": round(100 * covered / outstanding, 1) if outstanding else None,
        "scope1": round(s1) if has else None, "scope2": round(s2) if has else None,
        "scope12": round(s1 + s2) if has else None,
        # Σ outstanding × score / Σ outstanding over the mortgages with a score (§6.1, pp. 167-168)
        "dq_score": round(scored_x / scored_out, 2) if scored_out else None,
        "n_scored": n_scored, "scored_outstanding_eur": round(scored_out),
        "by_score": {str(k): {"n": v["n"], "outstanding_eur": round(v["outstanding_eur"]),
                              "financed_tco2e": round(v["financed_tco2e"], 1)} for k, v in sorted(by_score.items())},
        "n_score_not_defined": dict(sorted(no_score.items())),
        "gaps": [{"reason": k, "n": v["n"], "outstanding_eur": round(v["outstanding_eur"])}
                 for k, v in sorted(gaps.items(), key=lambda kv: GAPS.index(kv[0]))],
        "property_value_basis": basis,
        "n_attribution_above_one": n_above,
    }
