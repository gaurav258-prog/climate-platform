"""Re-sourcing / origin-substitution engine — the counterfactual behind COGS-at-risk.

COGS-at-risk tells a buyer how much of the volume they paid for won't arrive because of climate hazard at
their sourcing origins. This answers the next question: could they cut that by shifting spend to a LOWER-risk
origin they ALREADY source from? For every commodity sourced from more than one scored origin it compares the
origins' yield-shocks and computes the COGS-at-risk that a bounded reallocation — moving up to a capped share
of spend from the highest-risk origin to the lowest-risk one — would avoid.

Honest by construction: it only reallocates among origins the buyer already buys from (no fabricated new
supplier region — a single-origin commodity is reported as needing a genuinely new origin, not given a fake
alternative); origins without a scored yield-shock are excluded from the comparison; and the reallocation is
capped so the number is an achievable near-term shift, not an instant 100% re-source. Uses only the existing
engine + the buyer's own book — no new data.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intelligence.supply_cogs import project_org_supply

# Bounded, realistic near-term reallocation: at most this share of a commodity's spend shifts origin.
REALLOC_CAP = 0.30

# Common ISO-2 origin codes → readable names (display only; unknown codes fall back to the code).
_ORIGIN_NAME = {
    "CI": "Côte d'Ivoire", "GH": "Ghana", "ES": "Spain", "PT": "Portugal", "US": "United States",
    "BR": "Brazil", "ID": "Indonesia", "IN": "India", "VN": "Vietnam", "CO": "Colombia", "PE": "Peru",
    "TR": "Türkiye", "MA": "Morocco", "IT": "Italy", "FR": "France", "GR": "Greece", "EG": "Egypt",
    "KE": "Kenya", "ET": "Ethiopia", "MX": "Mexico", "AR": "Argentina", "AU": "Australia", "CL": "Chile",
}


def _name(code: str | None) -> str:
    return _ORIGIN_NAME.get((code or "").upper(), code or "—")


def evaluate_commodity(commodity: str, origins: list[dict], cap: float = REALLOC_CAP) -> dict:
    """Pure reallocation math for one commodity. origins: [{origin, name, yield_shock_pct, spend_eur}] already
    filtered to scored, positive-spend origins. Returns one of:
      {kind: 'none'}                              → nothing sourced / unusable
      {kind: 'single', ...}                       → one origin, needs a genuinely new origin to diversify
      {kind: 'concentrated', current_cogs_...}    → already on the lowest-risk origin, no opportunity
      {kind: 'opportunity', ...}                  → a bounded reallocation that avoids COGS-at-risk
    """
    if not origins:
        return {"kind": "none"}
    total_spend = sum(o["spend_eur"] for o in origins)
    current_car = sum(o["yield_shock_pct"] / 100.0 * o["spend_eur"] for o in origins)
    if len(origins) < 2:
        return {"kind": "single", "commodity": commodity, "origin": origins[0]["name"],
                "yield_shock_pct": origins[0]["yield_shock_pct"], "cogs_at_risk_eur": round(current_car)}
    ordered = sorted(origins, key=lambda o: o["yield_shock_pct"])
    best, worst = ordered[0], ordered[-1]
    if worst["yield_shock_pct"] <= best["yield_shock_pct"]:
        return {"kind": "concentrated", "commodity": commodity, "current_cogs_at_risk_eur": round(current_car)}
    shift = min(worst["spend_eur"], cap * total_spend)
    avoidable = shift * (worst["yield_shock_pct"] - best["yield_shock_pct"]) / 100.0
    return {
        "kind": "opportunity", "commodity": commodity,
        "current_cogs_at_risk_eur": round(current_car),
        "avoidable_eur": round(avoidable),
        "avoidable_pct": round(100 * avoidable / current_car, 1) if current_car else 0,
        "full_reallocation_floor_eur": round(best["yield_shock_pct"] / 100.0 * total_spend),
        "shift_spend_eur": round(shift),
        "from_origin": worst["name"], "from_yield_shock_pct": worst["yield_shock_pct"],
        "to_origin": best["name"], "to_yield_shock_pct": best["yield_shock_pct"],
        "n_origins": len(origins),
    }


def resourcing_opportunities(session: Session, org_id: str, *, scenario: str = "baseline",
                             time_horizon: str = "current", realloc_cap: float = REALLOC_CAP) -> dict:
    """Per-commodity origin-substitution opportunities + a book rollup. Reallocates spend among the origins the
    buyer already sources, from the highest-risk to the lowest-risk, capped at REALLOC_CAP."""
    res = project_org_supply(session, org_id, scenario=scenario, time_horizon=time_horizon)

    # per (commodity, origin) spend from the buyer's own plots
    rows = session.execute(text("""
        SELECT co.name AS commodity, p.country AS origin, SUM(CAST(p.annual_spend_eur AS FLOAT)) AS spend
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = CAST(:o AS uuid) GROUP BY co.name, p.country
    """), {"o": org_id}).mappings().all()
    spend_by = {(r["commodity"], r["origin"]): float(r["spend"] or 0) for r in rows}

    opportunities = []
    single_origin = []
    total_current = total_avoidable = 0.0

    for c in res.commodities:
        # origins with a scored yield-shock AND a positive spend we can move
        origins = [{"origin": o.get("origin"), "name": _name(o.get("origin")),
                    "yield_shock_pct": round(o["yield_shock_pct"], 2),
                    "spend_eur": round(spend_by.get((c.commodity, o.get("origin")), 0.0))}
                   for o in c.origins
                   if o.get("yield_shock_pct") is not None and spend_by.get((c.commodity, o.get("origin")), 0.0) > 0]
        ev = evaluate_commodity(c.commodity, origins, cap=realloc_cap)
        if ev["kind"] == "none":
            continue
        total_current += ev.get("current_cogs_at_risk_eur", 0) if ev["kind"] != "single" else ev["cogs_at_risk_eur"]
        if ev["kind"] == "single":
            single_origin.append(ev)
        elif ev["kind"] == "opportunity":
            total_avoidable += ev["avoidable_eur"]
            opportunities.append(ev)

    opportunities.sort(key=lambda x: -x["avoidable_eur"])
    return {
        "available": bool(opportunities or single_origin),
        "scenario": scenario, "time_horizon": time_horizon,
        "reallocation_cap_pct": round(realloc_cap * 100),
        "total_current_cogs_at_risk_eur": round(total_current),
        "total_avoidable_eur": round(total_avoidable),
        "avoidable_pct_of_current": round(100 * total_avoidable / total_current, 1) if total_current else 0,
        "n_opportunities": len(opportunities),
        "opportunities": opportunities,
        "single_origin_commodities": sorted(single_origin, key=lambda x: -x["cogs_at_risk_eur"])[:8],
        "method": ("Reallocates a bounded share (≤{cap}%) of each commodity's spend from its highest-risk to "
                   "its lowest-risk EXISTING origin; the avoided COGS-at-risk is shift × the yield-shock gap. "
                   "Only origins the buyer already sources are used — a single-origin commodity needs a "
                   "genuinely new origin, and is listed as such, never given a fabricated alternative.").format(
                       cap=round(realloc_cap * 100)),
    }
