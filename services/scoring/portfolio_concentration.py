"""Asset-management climate-risk CONCENTRATION — the diversification lens on the holdings book.

An asset manager's first discipline is diversification: not the sum of independent position losses, but whether
one event moves many positions at once. The combined climate-VaR already fattens the tail when positions are set
to move together (its `dependence` switch), but it never says WHERE the concentration is — which hazard, which
region, which cluster of names would be hit by a single shock. This overlay is that diagnostic: it decomposes the
portfolio's climate value-at-risk by hazard and by region, measures how concentrated the book is (a
Herfindahl index and the effective number of independent climate "bets"), and surfaces the single largest
common-shock cluster — the positions sharing one hazard in one place that a single event hits together.

Honest by construction. Every figure is a straight decomposition of quantities the portfolio engine already
produces — each holding's modelled climate VaR (position value − climate-discounted value), its headline hazard,
and its region. No new model, no assumed correlation matrix: the common-shock cluster is defined structurally
(same headline hazard × same region), and holdings not yet scored are reported as coverage, never assumed safe.
"""
from __future__ import annotations

from collections import defaultdict

_TOP_REGION_CONC_PCT = 25.0     # a single region above this share flags a geographic concentration
_TOP_HAZARD_CONC_PCT = 40.0     # a single hazard above this share flags a peril concentration
_LOW_DIVERSIFICATION_N = 5.0    # fewer than this many effective independent bets flags low diversification


def _hhi_and_effective(shares: list[float]) -> tuple[float, float]:
    """Herfindahl-Hirschman index over value shares (0-1) and the effective number of independent units (1/HHI)."""
    hhi = sum(s * s for s in shares)
    return round(hhi, 4), (round(1.0 / hhi, 1) if hhi else None)


def portfolio_concentration(holdings: list[dict]) -> dict:
    """holdings: the AM book (each with position_value_eur, climate_var.discounted_value_eur, headline_hazard,
    headline_bucket, region). Returns the concentration decomposition of the portfolio's climate VaR."""
    total_value = sum(h.get("position_value_eur") or 0 for h in holdings)
    if not total_value:
        return {"available": False, "reason": "empty_book"}

    def _var(h):   # modelled climate value-at-risk on this holding (€)
        return (h.get("position_value_eur") or 0) - (h.get("climate_var") or {}).get("discounted_value_eur", h.get("position_value_eur") or 0)

    total_var = sum(_var(h) for h in holdings)
    scored = [h for h in holdings if h.get("headline_bucket")]
    n_unscored = len(holdings) - len(scored)

    by_region: dict = defaultdict(lambda: {"value": 0.0, "var": 0.0, "n": 0})
    by_hazard: dict = defaultdict(lambda: {"value": 0.0, "var": 0.0, "n": 0})
    clusters: dict = defaultdict(lambda: {"value": 0.0, "var": 0.0, "n": 0})
    for h in holdings:
        v, vr = h.get("position_value_eur") or 0, _var(h)
        region = h.get("region") or "unspecified"
        by_region[region]["value"] += v; by_region[region]["var"] += vr; by_region[region]["n"] += 1
        hz = h.get("headline_hazard")
        if hz:   # only scored holdings carry a headline hazard / cluster
            by_hazard[hz]["value"] += v; by_hazard[hz]["var"] += vr; by_hazard[hz]["n"] += 1
            key = (hz, region)
            clusters[key]["value"] += v; clusters[key]["var"] += vr; clusters[key]["n"] += 1

    region_hhi, eff_regions = _hhi_and_effective([r["value"] / total_value for r in by_region.values()])
    scored_value = sum(h["value"] for h in by_hazard.values()) or 0
    hazard_hhi, eff_hazards = _hhi_and_effective(
        [h["value"] / scored_value for h in by_hazard.values()]) if scored_value else (None, None)

    regions = sorted(({"region": k, "value_eur": round(v["value"]), "climate_var_eur": round(v["var"]), "n": v["n"],
                       "pct_of_book": round(100 * v["value"] / total_value, 1)}
                      for k, v in by_region.items()), key=lambda r: -r["value_eur"])
    hazards = sorted(({"hazard": k, "value_eur": round(v["value"]), "climate_var_eur": round(v["var"]), "n": v["n"],
                       "pct_of_scored": round(100 * v["value"] / scored_value, 1) if scored_value else 0.0}
                     for k, v in by_hazard.items()), key=lambda r: -r["climate_var_eur"])
    cluster_list = sorted(({"hazard": k[0], "region": k[1], "value_eur": round(v["value"]),
                            "climate_var_eur": round(v["var"]), "n": v["n"],
                            "pct_of_book": round(100 * v["value"] / total_value, 1)}
                           for k, v in clusters.items()), key=lambda c: -c["climate_var_eur"])

    top_region = regions[0] if regions else None
    top_hazard = hazards[0] if hazards else None
    top_cluster = cluster_list[0] if cluster_list else None

    flags = []
    if top_region and top_region["pct_of_book"] > _TOP_REGION_CONC_PCT:
        flags.append(f"Geographic concentration: {top_region['pct_of_book']}% of the book in {top_region['region']}")
    if top_hazard and top_hazard["pct_of_scored"] > _TOP_HAZARD_CONC_PCT:
        flags.append(f"Peril concentration: {top_hazard['pct_of_scored']}% of scored value led by {top_hazard['hazard']}")
    if eff_regions is not None and eff_regions < _LOW_DIVERSIFICATION_N:
        flags.append(f"Low diversification: only {eff_regions} effective independent regions")

    return {
        "available": True,
        "total_value_eur": round(total_value),
        "total_climate_var_eur": round(total_var),
        "n_scored": len(scored), "n_unscored": n_unscored,
        "coverage_pct": round(100 * len(scored) / len(holdings), 1) if holdings else 0.0,
        "region_hhi": region_hhi, "effective_regions": eff_regions,
        "hazard_hhi": hazard_hhi, "effective_hazards": eff_hazards,
        "top_region": top_region, "top_hazard": top_hazard,
        # the single largest common-shock cluster — the positions one event (this hazard, this region) hits at once
        "common_shock": top_cluster,
        "common_shock_var_pct_of_total": round(100 * top_cluster["climate_var_eur"] / total_var, 1)
            if (top_cluster and total_var) else 0.0,
        "by_region": regions[:10],
        "by_hazard": hazards,
        "clusters": cluster_list[:8],   # the decision list — largest common-shock exposures to hedge / trim / diversify
        "flags": flags,
        "method": ("Concentration decomposes the portfolio's modelled climate VaR (position value − climate-"
                   "discounted value) by region and by headline hazard. HHI is the Herfindahl index over value "
                   "shares; effective count = 1/HHI (the number of equally-weighted independent bets the book "
                   "behaves like). A common-shock cluster is one headline hazard in one region — positions a "
                   "single event hits together. Structural definition, not a fitted correlation matrix; unscored "
                   "holdings are reported as coverage, never assumed safe."),
    }
