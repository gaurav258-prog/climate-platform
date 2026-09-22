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


def attributed_financed_emissions(rows: list[dict], *, exposure_key: str, evic_key: str,
                                  scope_keys: tuple[str, str, str] = ("ghg1", "ghg2", "ghg3")) -> dict:
    """rows: any book of counterparty-level dicts carrying an exposure field, an EVIC field, and scope1-3 GHG
    fields. Splits the book into EVIC-covered (real PCAF attribution) and not-covered (raw, un-attributed,
    disclosed separately — never silently summed into the attributed figure or hidden)."""
    attributed = {"scope1": 0.0, "scope2": 0.0, "scope3": 0.0}
    not_covered = {"scope1": 0.0, "scope2": 0.0, "scope3": 0.0}
    n_covered = n_not_covered = 0
    covered_exposure_eur = 0.0
    for r in rows:
        exp, evic = r.get(exposure_key), r.get(evic_key)
        g1, g2, g3 = (r.get(scope_keys[0]) or 0), (r.get(scope_keys[1]) or 0), (r.get(scope_keys[2]) or 0)
        if not (g1 or g2 or g3):
            continue   # no emissions on record at all -- not a coverage gap, nothing to attribute
        af = attribution_factor(exp, evic)
        if af is None:
            not_covered["scope1"] += g1; not_covered["scope2"] += g2; not_covered["scope3"] += g3
            n_not_covered += 1
        else:
            attributed["scope1"] += af * g1; attributed["scope2"] += af * g2; attributed["scope3"] += af * g3
            n_covered += 1
            covered_exposure_eur += exp or 0
    n_total = n_covered + n_not_covered
    return {
        "attributed": {k: round(v) for k, v in attributed.items()},
        "attributed_total": round(sum(attributed.values())),
        "not_covered": {k: round(v) for k, v in not_covered.items()},
        "not_covered_total": round(sum(not_covered.values())),
        "n_counterparties_with_emissions": n_total,
        "n_evic_covered": n_covered,
        "evic_coverage_pct": round(100 * n_covered / n_total, 1) if n_total else 0.0,
        "covered_exposure_eur": round(covered_exposure_eur),
    }
