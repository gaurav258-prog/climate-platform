"""PCAF attribution — the ONE formula shared by every vertical that claims a PCAF-attributed financed-emissions
figure (bank loan book here; asset-manager fund holdings in services/fund_disclosure.py, which this mirrors
exactly so the platform has one PCAF computation, not two that could drift apart).

Attribution factor = investment (or outstanding loan balance) / EVIC (Enterprise Value Including Cash),
capped at 1.0 — you cannot finance more than 100% of a counterparty, and a tiny or mis-keyed EVIC would
otherwise inflate financed emissions arbitrarily. EVIC must be strictly positive to be used at all.
"""
from __future__ import annotations

from typing import Optional


def attribution_factor(exposure_eur: Optional[float], evic_eur: Optional[float]) -> Optional[float]:
    """None when either side is missing or EVIC <= 0 — never a guessed/default weight."""
    if exposure_eur is None or evic_eur is None or evic_eur <= 0:
        return None
    return min(exposure_eur / evic_eur, 1.0)


_SCOPES = ("scope1", "scope2", "scope3")


def _stated(v) -> Optional[float]:
    """A stated emissions figure (0 is a figure); None when the counterparty states nothing for that scope."""
    return None if v is None or v == "" else float(v)


def gross_emissions(rows: list[dict], scope_keys: tuple[str, str, str] = ("ghg1", "ghg2", "ghg3"),
                    exposure_key: Optional[str] = None) -> dict:
    """The gross (un-attributed) emissions of a book, per scope, over the counterparties that STATE that scope — never
    a missing figure counted as 0 (E76). A scope no counterparty states has no total (None). The scope 1-3 total sums
    the counterparties stating all three — never scope 1 of one and scope 3 of another (E79). Returns the coverage with
    the figures: how many counterparties state any scope / each scope / all three, and the share of exposure."""
    totals: dict[str, Optional[float]] = {k: None for k in _SCOPES}
    n_scope = {k: 0 for k in _SCOPES}
    n_with = n_all = 0
    total = None
    exp_with = exp_all = exp_complete = 0.0
    for r in rows:
        vals = [_stated(r.get(k)) for k in scope_keys]
        exp = float(r.get(exposure_key) or 0) if exposure_key else 0.0
        exp_all += exp
        if all(v is None for v in vals):
            continue
        n_with += 1
        exp_with += exp
        for name, v in zip(_SCOPES, vals):
            if v is not None:
                totals[name] = (totals[name] or 0.0) + v
                n_scope[name] += 1
        if all(v is not None for v in vals):
            n_all += 1
            exp_complete += exp
            total = (total or 0.0) + sum(vals)
    return {**{k: (None if v is None else round(v)) for k, v in totals.items()},
            "total": None if total is None else round(total), "n_all_scopes": n_all,
            "n_counterparties": len(rows), "n_with_emissions": n_with, "n_stating": n_scope,
            **({"exposure_with_emissions_pct": round(100 * exp_with / exp_all, 1) if exp_all else None,
                "exposure_all_scopes_pct": round(100 * exp_complete / exp_all, 1) if exp_all else None}
               if exposure_key else {})}


def financed_total(em: dict) -> Optional[float]:
    """The scope 1-3 total of a frozen financed-emissions block. A block frozen since E79 carries its own 'total'
    (counterparties stating all three scopes); an older filing is re-read as it was filed — the sum of its scopes."""
    if "total" in em:
        return em["total"]
    vals = [em.get(k) for k in _SCOPES]
    return float(sum(v or 0 for v in vals)) if any(v is not None for v in vals) else None


def attributed_financed_emissions(rows: list[dict], *, exposure_key: str, evic_key: str,
                                  scope_keys: tuple[str, str, str] = ("ghg1", "ghg2", "ghg3")) -> dict:
    """rows: any book of counterparty-level dicts carrying an exposure field, an EVIC field, and scope 1-3 GHG fields.
    Splits the counterparties that state emissions into EVIC-covered (real PCAF attribution) and not covered (raw,
    un-attributed, disclosed separately — never silently summed into the attributed figure or hidden). A scope a
    counterparty does not state is not counted (never 0); a counterparty stating none is reported as without
    emissions data, with the share of exposure that carries data (E76)."""
    attributed: dict[str, Optional[float]] = {k: None for k in _SCOPES}
    not_covered: dict[str, Optional[float]] = {k: None for k in _SCOPES}
    # the scope 1-3 totals sum counterparties stating all three scopes (E79)
    att_total = nc_total = None
    n_covered = n_not_covered = n_att_all = 0
    covered_exposure_eur = att_all_exposure_eur = 0.0
    for r in rows:
        exp, evic = r.get(exposure_key), r.get(evic_key)
        vals = [_stated(r.get(k)) for k in scope_keys]
        if all(v is None for v in vals):
            continue   # no emissions on record — reported in the coverage below, never as zero emissions
        af = attribution_factor(exp, evic)
        for name, v in zip(_SCOPES, vals):
            if v is None:
                continue
            if af is None:
                not_covered[name] = (not_covered[name] or 0.0) + v
            else:
                attributed[name] = (attributed[name] or 0.0) + af * v
        complete = all(v is not None for v in vals)
        if af is None:
            n_not_covered += 1
            if complete:
                nc_total = (nc_total or 0.0) + sum(vals)
        else:
            n_covered += 1
            covered_exposure_eur += exp or 0
            if complete:
                n_att_all += 1
                att_all_exposure_eur += exp or 0
                att_total = (att_total or 0.0) + af * sum(vals)
    n_total = n_covered + n_not_covered
    gross = gross_emissions(rows, scope_keys, exposure_key)
    def _r(v):
        return None if v is None else round(v)
    return {
        # per scope over the EVIC-covered counterparties stating it; 'total' over those stating all three
        "attributed": {**{k: _r(v) for k, v in attributed.items()}, "total": _r(att_total)},
        "attributed_total": _r(att_total),
        "n_attributed_all_scopes": n_att_all,
        "attributed_all_scopes_exposure_eur": round(att_all_exposure_eur),
        "not_covered": {**{k: _r(v) for k, v in not_covered.items()}, "total": _r(nc_total)},
        "not_covered_total": _r(nc_total),
        "n_counterparties": len(rows),
        "n_counterparties_with_emissions": n_total,
        "n_stating": gross["n_stating"],
        "exposure_with_emissions_pct": gross["exposure_with_emissions_pct"],
        "n_evic_covered": n_covered,
        "evic_coverage_pct": round(100 * n_covered / n_total, 1) if n_total else None,
        "covered_exposure_eur": round(covered_exposure_eur),
    }


def _add(*vals: Optional[float]) -> Optional[float]:
    """A sum over the figures that exist (a missing one is not 0); None when none exists."""
    got = [v for v in vals if v is not None]
    return round(sum(got)) if got else None


def book_financed_emissions(rows: list[dict], *, exposure_key: str, evic_key: str,
                            scope_keys: tuple[str, str, str] = ("ghg1", "ghg2", "ghg3")) -> dict:
    """A loan book's financed emissions, each loan by the method of its PCAF asset class (Part A, 3rd ed., chapter 5;
    data/reference/pcaf/part_a_2025.json):

      enterprise value   listed equity and bonds, business loans — and a loan whose class is not stated (the book as it
                         was before the class was asked): attributed_financed_emissions above, its keys at the top level
      mortgages          services/scoring/pcaf_mortgages.book: the building's scope 1 and 2 by its property value at
                         origination ('mortgages', with the weighted data quality score)
      not built          any other class: counted with its outstanding amount under 'not_built', never attributed by an
                         enterprise value its method does not use

    'combined' keeps the shape every reader takes (scope1, scope2, scope3, total): scope 1 and scope 2 over both methods;
    scope 3 the companies' (§5.5 covers a mortgage's scope 1 and 2 only); total the companies stating all three scopes
    (E79) plus the mortgages' scope 1 and 2 — each class over the scopes its method covers (Table 10.2-2, p. 199).
    'class_not_stated' counts the loans whose counterparty has no enterprise value (a household, government or central
    bank) and whose class is not stated — no method can attribute them."""
    from services.ingest.sector_ingest import NO_ENTERPRISE_VALUE
    from services.scoring import pcaf_mortgages as pm
    evic_rows: list[dict] = []
    not_built: dict[str, dict] = {}
    unstated = {"n": 0, "outstanding_eur": 0.0}
    for r in rows:
        cls = r.get("pcaf_asset_class")
        method = pm.method_of(cls) if cls else "evic"
        if method == "evic":
            evic_rows.append(r)
            if cls is None and r.get(evic_key) is None and r.get("counterparty_sector") in NO_ENTERPRISE_VALUE:
                unstated["n"] += 1
                unstated["outstanding_eur"] += float(r.get(exposure_key) or 0)
        elif method is None:
            nb = not_built.setdefault(cls, {"n": 0, "outstanding_eur": 0.0})
            nb["n"] += 1
            nb["outstanding_eur"] += float(r.get(exposure_key) or 0)
    out = attributed_financed_emissions(evic_rows, exposure_key=exposure_key, evic_key=evic_key, scope_keys=scope_keys)
    mort = pm.book(rows)
    att = out["attributed"]
    out["mortgages"] = mort
    out["not_built"] = [{"asset_class": k, "n": v["n"], "outstanding_eur": round(v["outstanding_eur"])}
                        for k, v in sorted(not_built.items())]
    out["class_not_stated"] = {"n": unstated["n"], "outstanding_eur": round(unstated["outstanding_eur"])}
    out["combined"] = {"scope1": _add(att["scope1"], mort["scope1"]), "scope2": _add(att["scope2"], mort["scope2"]),
                       "scope3": att["scope3"], "total": _add(att["total"], mort["scope12"])}
    return out


def asset_financed(a: dict, *, exposure_key: str = "outstanding_loan_balance_eur", evic_key: str = "evic_eur",
                   scope_keys: tuple[str, str, str] = ("ghg1", "ghg2", "ghg3")) -> dict:
    """One loan's part of the book's financed emissions, by the rules the book sums ('combined' above): per scope the
    attributed figure of a scope the counterparty states; 'total' only where the book's total counts the loan — a
    company stating all three scopes (E79), or a mortgage with its scope 1 and 2. None where the book does not count it
    (no enterprise value, a gap, a class not built) — never a missing scope read as 0."""
    from services.scoring import pcaf_mortgages as pm
    none = {"scope1": None, "scope2": None, "scope3": None, "total": None}
    cls = a.get("pcaf_asset_class")
    method = pm.method_of(cls) if cls else "evic"
    if method == "mortgage":
        m = a.get("pcaf_mortgage") or pm.loan(a)
        if m.get("gaps"):
            return none
        return {"scope1": m["financed_scope1_tco2e"], "scope2": m["financed_scope2_tco2e"], "scope3": None,
                "total": m["financed_tco2e"]}
    if method != "evic":
        return none
    af = attribution_factor(a.get(exposure_key), a.get(evic_key))
    if af is None:
        return none
    vals = [_stated(a.get(k)) for k in scope_keys]
    out = {name: None if v is None else af * v for name, v in zip(_SCOPES, vals)}
    out["total"] = af * sum(vals) if all(v is not None for v in vals) else None
    return out
