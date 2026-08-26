"""Agriculture's missing dimension — SUPPLY-SHOCK concentration.

The COGS engine tells a buyer how much sourcing spend is at risk. What it does not answer is the buyer's first
resilience question: is that risk CONCENTRATED — does one crop, or one climate hazard, carry a big share of the
book, so a single bad season takes out a lot at once? This is the sourcing analogue of the asset-manager's
portfolio concentration and the insurer's catastrophe accumulation: decompose the book by commodity and by
hazard, measure how concentrated it is (a Herfindahl index and the effective number of independent sourcing
"bets"), and surface the single largest common shock — the one climate hazard that would hit the most sourcing
spend across crops simultaneously.

Honest by construction. The concentration base is SPEND (exposure), which is always known — never the withheld
€. The published COGS-at-risk is shown alongside only where the crop's chain is event-backtested (status
'scored'); a 'held'/'pending' crop contributes its exposure but no fabricated euro, exactly as the COGS engine
gates it. Structural common-shock (one hazard across the crops it drives), not a fitted correlation matrix.
"""
from __future__ import annotations

from collections import defaultdict


def _g(c, k, default=None):
    """Read a field from a CommodityRisk object OR its asdict() dict."""
    return getattr(c, k, default) if not isinstance(c, dict) else c.get(k, default)


def _hhi_effective(shares: list[float]) -> tuple[float, float | None]:
    hhi = sum(s * s for s in shares)
    return round(hhi, 4), (round(1.0 / hhi, 1) if hhi else None)


_TOP_COMMODITY_PCT = 25.0   # a single crop above this share of spend flags a concentration
_TOP_HAZARD_PCT = 40.0      # a single hazard above this share of spend flags a peril concentration
_LOW_DIVERSIFICATION_N = 3.0


def supply_concentration(commodities: list) -> dict:
    """commodities: the projected sourcing book (CommodityRisk objects or their asdict() dicts, each with
    commodity, annual_spend_eur, top_hazard, status, cogs_at_risk_p50 / volume_at_risk_eur). Returns the
    concentration decomposition of the sourcing book by crop and by hazard."""
    total_spend = sum(_g(c, "annual_spend_eur") or 0 for c in commodities)
    if not total_spend:
        return {"available": False, "reason": "no_sourcing_spend"}

    def _published_at_risk(c):   # € only where the crop is event-backtested; else None (never fabricated)
        if _g(c, "status") != "scored":
            return None
        return _g(c, "cogs_at_risk_p50") if _g(c, "cogs_at_risk_p50") is not None else _g(c, "volume_at_risk_eur")

    by_hazard: dict = defaultdict(lambda: {"spend": 0.0, "at_risk": 0.0, "n": 0, "commodities": []})
    commodity_rows = []
    total_published = 0.0
    for c in commodities:
        spend = _g(c, "annual_spend_eur") or 0
        hz = _g(c, "top_hazard") or "unscored"
        ar = _published_at_risk(c)
        if ar:
            total_published += ar
        by_hazard[hz]["spend"] += spend
        by_hazard[hz]["at_risk"] += ar or 0
        by_hazard[hz]["n"] += 1
        by_hazard[hz]["commodities"].append(_g(c, "commodity"))
        commodity_rows.append({
            "commodity": _g(c, "commodity"), "spend_eur": round(spend),
            "pct_of_spend": round(100 * spend / total_spend, 1),
            "top_hazard": _g(c, "top_hazard"), "status": _g(c, "status"),
            "at_risk_eur": round(ar) if ar else None,
        })

    commodity_rows.sort(key=lambda r: -r["spend_eur"])
    commodity_hhi, eff_commodities = _hhi_effective([(_g(c, "annual_spend_eur") or 0) / total_spend for c in commodities])
    hazard_hhi, eff_hazards = _hhi_effective([h["spend"] / total_spend for h in by_hazard.values()])

    hazard_rows = sorted(({"hazard": k, "spend_eur": round(v["spend"]), "at_risk_eur": round(v["at_risk"]) or None,
                           "n_commodities": v["n"], "pct_of_spend": round(100 * v["spend"] / total_spend, 1),
                           "commodities": v["commodities"][:6]}
                          for k, v in by_hazard.items() if k != "unscored"),
                         key=lambda r: -r["spend_eur"])

    top_commodity = commodity_rows[0] if commodity_rows else None
    # the single largest common shock — one hazard across every crop it drives
    common_shock = hazard_rows[0] if hazard_rows else None

    flags = []
    if top_commodity and top_commodity["pct_of_spend"] > _TOP_COMMODITY_PCT:
        flags.append(f"Crop concentration: {top_commodity['pct_of_spend']}% of spend in {top_commodity['commodity']}")
    if common_shock and common_shock["pct_of_spend"] > _TOP_HAZARD_PCT:
        flags.append(f"Peril concentration: {common_shock['pct_of_spend']}% of spend exposed to {common_shock['hazard']}")
    if eff_commodities is not None and eff_commodities < _LOW_DIVERSIFICATION_N:
        flags.append(f"Low diversification: only {eff_commodities} effective independent crops")

    return {
        "available": True,
        "total_spend_eur": round(total_spend),
        "total_published_at_risk_eur": round(total_published),
        "commodity_hhi": commodity_hhi, "effective_commodities": eff_commodities,
        "hazard_hhi": hazard_hhi, "effective_hazards": eff_hazards,
        "top_commodity": top_commodity,
        "common_shock": common_shock,
        "common_shock_pct_of_spend": common_shock["pct_of_spend"] if common_shock else 0.0,
        "by_commodity": commodity_rows[:10],
        "by_hazard": hazard_rows,
        "flags": flags,
        "method": ("Concentration decomposes the sourcing book by crop and by climate hazard on SPEND (exposure, "
                   "always known); published COGS-at-risk is shown only where the crop is event-backtested, never "
                   "fabricated for a held/pending crop. HHI is the Herfindahl index over spend shares; effective "
                   "count = 1/HHI. A common shock is one hazard across the crops it drives — the sourcing a single "
                   "bad season would hit together. Structural, not a fitted correlation matrix."),
    }
