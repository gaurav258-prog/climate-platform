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
    a missing figure counted as 0 (E76). A scope no counterparty states has no total (None). Returns the coverage with
    the figure: how many counterparties state any scope / each scope, and the share of exposure they carry."""
    totals: dict[str, Optional[float]] = {k: None for k in _SCOPES}
    n_scope = {k: 0 for k in _SCOPES}
    n_with = 0
    exp_with = exp_all = 0.0
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
    stated = [v for v in totals.values() if v is not None]
    return {**{k: (None if v is None else round(v)) for k, v in totals.items()},
            "total": round(sum(stated)) if stated else None,
            "n_counterparties": len(rows), "n_with_emissions": n_with, "n_stating": n_scope,
            **({"exposure_with_emissions_pct": round(100 * exp_with / exp_all, 1) if exp_all else None} if exposure_key else {})}


def attributed_financed_emissions(rows: list[dict], *, exposure_key: str, evic_key: str,
                                  scope_keys: tuple[str, str, str] = ("ghg1", "ghg2", "ghg3")) -> dict:
    """rows: any book of counterparty-level dicts carrying an exposure field, an EVIC field, and scope 1-3 GHG fields.
    Splits the counterparties that state emissions into EVIC-covered (real PCAF attribution) and not covered (raw,
    un-attributed, disclosed separately — never silently summed into the attributed figure or hidden). A scope a
    counterparty does not state is not counted (never 0); a counterparty stating none is reported as without
    emissions data, with the share of exposure that carries data (E76)."""
    attributed = {k: 0.0 for k in _SCOPES}
    not_covered = {k: 0.0 for k in _SCOPES}
    n_covered = n_not_covered = 0
    covered_exposure_eur = 0.0
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
                not_covered[name] += v
            else:
                attributed[name] += af * v
        if af is None:
            n_not_covered += 1
        else:
            n_covered += 1
            covered_exposure_eur += exp or 0
    n_total = n_covered + n_not_covered
    gross = gross_emissions(rows, scope_keys, exposure_key)
    return {
        "attributed": {k: round(v) for k, v in attributed.items()},
        "attributed_total": round(sum(attributed.values())),
        "not_covered": {k: round(v) for k, v in not_covered.items()},
        "not_covered_total": round(sum(not_covered.values())),
        "n_counterparties": len(rows),
        "n_counterparties_with_emissions": n_total,
        "n_stating": gross["n_stating"],
        "exposure_with_emissions_pct": gross["exposure_with_emissions_pct"],
        "n_evic_covered": n_covered,
        "evic_coverage_pct": round(100 * n_covered / n_total, 1) if n_total else None,
        "covered_exposure_eur": round(covered_exposure_eur),
    }
