"""
Supply-chain "COGS-at-risk" — the impact-function layer (v0).

Turns a plot's projected climate hazard (from canonical_scores, via
v_sc_plot_physical_risk) into a euro figure on cost-of-goods, rolled up the bill
of materials. Implements the chain in docs/SUPPLY_CHAIN_IMPACT_FUNCTION_METHODOLOGY.md:
    hazard intensity → yield shock → price response → cost inflation (€) → roll up BOM
with the three channels kept separate (Market / Sourcing / Continuity) and a P50–P90 range.

HONESTY (v0, per the methodology's governance §8):
- This is an UNCALIBRATED v0. It uses the 0–100 canonical score as a PROXY for hazard
  intensity; production must consume physical stressors (heat-days, SPEI) per §1.1, and each
  commodity's functions must pass the event backtest (§6) before its € is shown as validated.
- Commodities whose plots are unscored (e.g. cocoa — drought/heat pending) are returned with
  status='pending' and NO euro figure — exposure is mapped, € is withheld. Never a silent zero.
Every figure carries IMPACT_VERSION so it is reproducible and clearly marked provisional.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

IMPACT_VERSION = "sc-impact-v0.2"

# v0 crop climate-sensitivity (fraction of yield lost at full hazard). Illustrative,
# pending calibration against yield–weather panels (methodology §1.2).
CROP_SENSITIVITY = {
    "Olive oil": 0.35, "Citrus": 0.45, "Almonds": 0.40, "Durum wheat": 0.40,
    "Wine grapes": 0.45, "Cane sugar": 0.35, "Cocoa": 0.55,
}
DEFAULT_SENSITIVITY = 0.40
TRANSMISSION = 0.5      # fallback transmission when a commodity carries no stock-to-use (v0)
SOURCING_PREMIUM = 0.12  # idiosyncratic cover/premium as a fraction of yield-shock (v0)
PRICE_MOVE_CAP = 3.0     # cap the modelled price move at +300% (cocoa 2024 peaked ~ there)
P90_FACTOR = 1.8         # width of the reported range (uncertainty propagation proxy, v0)

# Per-commodity CALIBRATED parameters (v0.2). Others fall back to CROP_SENSITIVITY,
# global_share=1.0 (local shock ≈ price shock) and flat transmission — i.e. UNCHANGED.
#   market channel: price_move = A(stock_to_use) × (yield_shock × global_share) / |elasticity|
# Cocoa is calibrated to reproduce the real 2023/24 event end-to-end, on the SEASONAL
# (Jan–Mar harmattan) heat score = 73 (heat-climatology-v1-seasonal):
#   heat 73 → yield_shock ≈ 0.294×0.73 = 21.5%; × 60% world share = 12.9% global supply shock
#   (= ICCO −12.9%); × A(26% stocks)=2.69 / η=0.20 → +173% (≈ observed +177% 2024 avg; P90 ≈ peak).
# (sensitivity re-held from 0.37→0.294 when scoring moved annual→seasonal; the event target is
#  fixed, the heat→yield coefficient is the fitted free parameter.)
COMMODITY_PARAMS = {
    "Cocoa": {"sensitivity": 0.294, "global_share": 0.60, "stock_to_use": 26.4},
    # Coffee (arabica) — calibrated to the DROUGHT share of the 2021 event:
    #   drought score ≈ 80 (2021 SPEI −0.86) × 0.45 = yield-shock 36% × 35% Brazil share =
    #   12.7% global supply shock (= observed −12.7%); × A(40% stocks)=0.60 / η=0.28 → +27%.
    #   That's the drought-attributable move; the Jul-2021 FROST added the rest (to ~+60%) and
    #   is NOT modelled (pending the CDS daily-min fix) — so coffee's € is a conservative floor.
    "Coffee": {"sensitivity": 0.45, "global_share": 0.35, "stock_to_use": 40.0},
}
_DEFAULT_PARAMS = {"sensitivity": None, "global_share": 1.0, "stock_to_use": None}


@dataclass
class CommodityRisk:
    commodity: str
    eudr_covered: bool
    annual_spend_eur: float
    n_plots: int
    n_plots_scored: int
    status: str                      # 'scored' | 'pending'
    avg_hazard: Optional[float] = None
    top_hazard: Optional[str] = None
    yield_shock_pct: Optional[float] = None
    global_share: Optional[float] = None
    price_move_pct: Optional[float] = None
    cogs_at_risk_p50: Optional[float] = None
    cogs_at_risk_p90: Optional[float] = None
    market_eur: Optional[float] = None
    sourcing_eur: Optional[float] = None


@dataclass
class PortfolioCogsAtRisk:
    ingredient_spend_eur: float
    total_cogs_eur: float
    cogs_at_risk_p50: float
    cogs_at_risk_p90: float
    pct_cogs_at_risk: float
    n_commodities: int
    n_pending: int
    commodities: list[CommodityRisk] = field(default_factory=list)
    impact_version: str = IMPACT_VERSION


def amplification(stock_to_use):
    """
    Stock-to-use price amplification A(s) — methodology §1.3, backtest-anchored (v0.1).
    Backtest (scripts/backtest_supply_impact.py) showed a CONSTANT transmission is wrong in
    low-stock regimes: cocoa 2023/24 (stocks ≈26%, 45-yr low) implied A≈2.7×, coffee 2021
    (stocks ≈40%) implied A≈0.6×. A(s) = (34.7/s)^3.62 passes through those two points — a
    DIRECTION, not a calibrated curve (two points); capped [0.3, 6.0] pending a full
    stocks-to-use panel. Falls back to the flat TRANSMISSION when stock-to-use is unknown
    (so the demo book, which carries no stock-to-use, is unchanged).
    """
    if not stock_to_use:
        return TRANSMISSION
    return max(0.3, min(6.0, (34.7 / stock_to_use) ** 3.62))


def _commodity_risk(name, eudr, spend, plots, elasticity, amp, sens, global_share) -> CommodityRisk:
    """plots: list of dicts {hazard→score} aggregated per plot (scored plots only carry hazards)."""
    scored = [p for p in plots if p.get("hazards")]
    n_plots, n_scored = len(plots), len(scored)
    if n_scored == 0:
        # exposure mapped, € pending (governance §8)
        return CommodityRisk(name, eudr, spend, n_plots, 0, status="pending")

    # spend-weighted worst-hazard score across the commodity's scored plots
    wsum = sum(p["spend"] for p in scored) or 1.0
    avg_hazard = sum(max(p["hazards"].values()) * p["spend"] for p in scored) / wsum
    top_hazard = max(
        ((hz, sc) for p in scored for hz, sc in p["hazards"].items()),
        key=lambda t: t[1],
    )[0]

    yield_shock = sens * (avg_hazard / 100.0)                       # §1.2 hazard → local yield shock
    global_shock = yield_shock * global_share                      # §1.3 local → world supply shock
    price_move = min(PRICE_MOVE_CAP, amp * global_shock / elasticity)  # §1.3 world shock → price (amplified)
    market = price_move * spend                                    # §1.4 market channel (all spend)
    sourcing = SOURCING_PREMIUM * yield_shock * spend              # §1.4 sourcing channel (own plots)
    p50 = market + sourcing
    return CommodityRisk(
        commodity=name, eudr_covered=eudr, annual_spend_eur=spend,
        n_plots=n_plots, n_plots_scored=n_scored, status="scored",
        avg_hazard=round(avg_hazard, 1), top_hazard=top_hazard,
        yield_shock_pct=round(yield_shock * 100, 1), global_share=global_share,
        price_move_pct=round(price_move * 100, 1),
        cogs_at_risk_p50=round(p50, 2), cogs_at_risk_p90=round(p50 * P90_FACTOR, 2),
        market_eur=round(market, 2), sourcing_eur=round(sourcing, 2),
    )


def compute(commodities: list[dict], total_cogs_eur: float) -> PortfolioCogsAtRisk:
    """
    Pure roll-up. `commodities` = list of
      {name, eudr_covered, elasticity, spend, plots:[{spend, hazards:{hz:score}}]}.
    Per-commodity calibration (sensitivity / global_share / stock_to_use) comes from
    COMMODITY_PARAMS; uncalibrated commodities keep the v0.1 behaviour.
    """
    risks: list[CommodityRisk] = []
    for c in commodities:
        p = {**_DEFAULT_PARAMS, **COMMODITY_PARAMS.get(c["name"], {})}
        elasticity = abs(c["elasticity"]) if c.get("elasticity") else 0.25
        stock = p["stock_to_use"] if p["stock_to_use"] is not None else c.get("stock_to_use")
        amp = amplification(stock)
        sens = p["sensitivity"] if p["sensitivity"] is not None else CROP_SENSITIVITY.get(c["name"], DEFAULT_SENSITIVITY)
        risks.append(_commodity_risk(c["name"], c["eudr_covered"], c["spend"], c["plots"],
                                     elasticity, amp, sens, p["global_share"]))

    scored = [r for r in risks if r.status == "scored"]
    p50 = sum(r.cogs_at_risk_p50 for r in scored)
    p90 = sum(r.cogs_at_risk_p90 for r in scored)
    spend = sum(r.annual_spend_eur for r in risks)
    risks.sort(key=lambda r: (r.cogs_at_risk_p50 or -1), reverse=True)
    return PortfolioCogsAtRisk(
        ingredient_spend_eur=round(spend, 2),
        total_cogs_eur=round(total_cogs_eur, 2),
        cogs_at_risk_p50=round(p50, 2),
        cogs_at_risk_p90=round(p90, 2),
        pct_cogs_at_risk=round(100 * p50 / total_cogs_eur, 2) if total_cogs_eur else 0.0,
        n_commodities=len(risks),
        n_pending=len([r for r in risks if r.status == "pending"]),
        commodities=risks,
    )


# ── DB adapter ───────────────────────────────────────────────────────────────

_GRAPH_SQL = """
    SELECT co.name AS commodity, co.eudr_covered, co.demand_elasticity AS elasticity,
           p.plot_id::text AS plot_id, p.annual_spend_eur AS plot_spend,
           v.hazard_type, v.physical_risk_score
    FROM   sc_sourcing_plots p
    JOIN   sc_commodities   co ON co.commodity_id = p.commodity_id
    LEFT   JOIN v_sc_plot_physical_risk v
           ON v.plot_id = p.plot_id AND v.scenario = :scenario AND v.time_horizon = :horizon
    WHERE  p.org_id = :org_id
"""


def project_org_supply(session, org_id: str, *, scenario="baseline", time_horizon="current") -> PortfolioCogsAtRisk:
    """DB-backed COGS-at-risk for one org's procurement book at a scenario × horizon."""
    from sqlalchemy import text

    rows = session.execute(text(_GRAPH_SQL), {
        "org_id": org_id, "scenario": scenario, "horizon": time_horizon,
    }).mappings().all()

    # group rows → commodity → plots → hazards
    by_commodity: dict[str, dict] = {}
    plots: dict[str, dict] = {}
    for r in rows:
        c = by_commodity.setdefault(r["commodity"], {
            "name": r["commodity"], "eudr_covered": r["eudr_covered"],
            "elasticity": float(r["elasticity"]) if r["elasticity"] is not None else None,
            "spend": 0.0, "_plots": {},
        })
        pl = c["_plots"].setdefault(r["plot_id"], {"spend": float(r["plot_spend"] or 0), "hazards": {}})
        if r["hazard_type"] is not None and r["physical_risk_score"] is not None:
            pl["hazards"][r["hazard_type"]] = float(r["physical_risk_score"])

    commodities = []
    for c in by_commodity.values():
        c["spend"] = sum(pl["spend"] for pl in c["_plots"].values())
        c["plots"] = list(c["_plots"].values())
        del c["_plots"]
        commodities.append(c)

    total_cogs = session.execute(
        __import__("sqlalchemy").text("SELECT COALESCE(SUM(annual_cogs_eur),0) FROM sc_products WHERE org_id=:o"),
        {"o": org_id},
    ).scalar() or 0.0
    return compute(commodities, float(total_cogs))
