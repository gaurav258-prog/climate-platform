"""
Supply-chain "COGS-at-risk" — the impact-function layer.

Turns a plot's projected climate hazard (from canonical_scores, via v_sc_plot_physical_risk)
into a euro figure on cost-of-goods, rolled up the bill of materials:
    hazard intensity → yield shock → VOLUME AT RISK (€ at the price they already pay)

WHAT CHANGED 2026-07-16, AND WHY IT MATTERS MORE THAN ANYTHING ELSE IN THIS FILE.
The chain used to end in a PRICE PREDICTION:
    price_move = A(stocks) × world_shock / |elasticity|;  market_€ = price_move × spend
and that market channel was 97.8% of every euro we published. We tested its premise against
440 real crop-years (USDA PSD production+stocks, World Bank prices, one consistent marketing
-year calendar):

    supply shock → price move :  r² = 0.018   (2% of price variation explained)
    stocks → amplification    :  r² = 0.041   (4%), empirical exponent 0.23 vs our 3.62

A harvest failure DOES push price up — 64% of 53 real contractions — but by how much is not
predictable from supply data. By the time production is measured, the market priced the news
months earlier. We were selling a forecast we cannot make, and it was almost the whole number.

So the headline is now the half we can prove:
    volume_at_risk = yield_shock × spend
The buyer's own plots lose that share of their yield, so that share of the volume they paid
for does not arrive. Valued at the price they ALREADY pay. No forecast in it. The hazard→yield
chain behind it IS validated against the real event (cocoa: modelled world shock 8.92% vs
FAO's measured 8.88%).

The price channel survives only as the BUYER'S OWN assumption (price_scenario_pct) — they
trade this daily and we do not. We apply their number and label it as theirs; we never
generate it.

GOVERNANCE — THE PUBLISH GATE (methodology §8, hard rule):
A euro figure leaves this engine ONLY if its hazard→yield chain has been reproduced against a
real, documented crop failure, for EVERY origin the buyer sources. There is no "illustrative
€": a number on a page gets used no matter what banner sits above it. So:
- status='scored'  → backtested. € published.
- status='held'    → scored, but the chain is not event-backtested for some origin.
                     Exposure and hazard driver shown; € WITHHELD (not shown behind a caveat).
- status='pending' → no hazard score yet. Exposure mapped, € withheld. Never a silent zero.
Held/pending exposure is reported as SPEND (a fact), never rolled into the € headline.
Every figure carries IMPACT_VERSION so it is reproducible.

GOVERNANCE — THE PUBLISH GATE (methodology §8, hard rule):
A euro figure leaves this engine ONLY if its hazard→yield→price chain has been reproduced
against a real, documented crop failure, for EVERY origin the buyer sources. There is no
"illustrative €": a number on a page gets used no matter what banner sits above it. So:
- status='scored'  → backtested. € published.
- status='held'    → scored, but the chain is not event-backtested for some origin.
                     Exposure and hazard driver shown; € WITHHELD (not shown behind a caveat).
- status='pending' → no hazard score yet. Exposure mapped, € withheld. Never a silent zero.
Held/pending exposure is reported as SPEND (a fact), never rolled into the € headline.
Every figure carries IMPACT_VERSION so it is reproducible.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ml.confidence_grade import grade as _grade

IMPACT_VERSION = "sc-impact-v0.5"

# A ranged crop's fit must explain at least this share of its climate-attributable variance to
# publish a € (as a band) — measured on OUT-OF-SAMPLE r² (r2_oos), the cross-validated "honest"
# number, NOT in-sample r². The DB tier view (ranged_gate_oos migration) and scripts/fit_ranged_crop.py
# gate on the same floor + metric. A weaker fit is stored + shown as "tested, below bar", € withheld.
RANGED_PUBLISH_FLOOR = 0.40

# v0 crop climate-sensitivity (fraction of yield lost at full hazard). Illustrative,
# pending calibration against yield–weather panels (methodology §1.2).
CROP_SENSITIVITY = {
    "Olive oil": 0.35, "Citrus": 0.45, "Almonds": 0.40, "Durum wheat": 0.40,
    "Wine grapes": 0.45, "Cane sugar": 0.35, "Cocoa": 0.55,
}
DEFAULT_SENSITIVITY = 0.40
TRANSMISSION = 0.5      # fallback transmission when a commodity carries no stock-to-use (v0)
# RETIRED 2026-07-16, all three were invented numbers dressed as parameters:
#   SOURCING_PREMIUM = 0.12  -> the sourcing channel is simply yield_shock x spend; there is no
#                               reason for a 0.12 haircut on the volume that fails to arrive.
#   PRICE_MOVE_CAP   = 3.0   -> capped a prediction we no longer make.
#   P90_FACTOR       = 1.8   -> a "P90" that was just p50 x 1.8. That is not a confidence
#                               interval, it is a decoration. We have no quantified uncertainty
#                               on the sensitivity, so we report none.

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
    # Coffee (arabica) — calibrated to the 2021 event, drought AND frost (COMPOUND_HAZARDS):
    #   drought score ≈ 80–86 (2021 SPEI −0.86) is the primary driver; the Jul-2021 FROST is now
    #   also scored (season-minimum daily 2m temp from raw hourly ERA5 — ml/scoring/frost_climatology,
    #   wired by scripts/wire_frost_demo.py on the same 2021 basis) and COMPOUNDS with drought on the
    #   Brazil plot via the independent-multiplicative-damage path in _plot_yield_shock. Combined the
    #   chain reproduces the real +44–60% 2021 move (methodology §6.3); drought alone is the lower
    #   bound. Frost reuses the drought-fitted sensitivity (no separate frost coefficient) — it is the
    #   COMBINED result that is validated against the event, not a standalone frost elasticity.
    "Coffee": {"sensitivity": 0.45, "global_share": 0.35, "stock_to_use": 40.0},

    # The remaining six commodities were previously left at global_share=1.0
    # (i.e. "this one sourcing region IS 100% of world supply") -- a much
    # cruder placeholder than a rough real approximation. These are NOT
    # event-backtested (still calibration='indicative', see BACKTESTED below)
    # -- sensitivity is left at CROP_SENSITIVITY's existing value, only
    # global_share and stock_to_use are added, from widely-cited public
    # production-share and USDA/FAO stocks-to-use figures:
    #   Olive oil: Spain ~45% of world olive oil production (IOC); oil stores
    #     well within a season, moderate carryover -> stock_to_use ~25%.
    #   Durum wheat: Spain/Andalusia is a minor global durum origin (Canada,
    #     Italy, Turkey dominate) -> global_share ~2%; wheat's global
    #     stock_to_use runs ~30-35% (USDA WASDE).
    #   Citrus: Valencia is a major EU citrus region but small next to
    #     Brazil/China/US -> global_share ~3%; citrus is highly perishable,
    #     low carryover -> stock_to_use ~12%.
    #   Wine grapes: Extremadura is a small fraction of world wine grape
    #     production (far more geographically diversified than cocoa/coffee)
    #     -> global_share ~1%; wine's multi-year aging inventory gives a
    #     higher stock_to_use ~45%.
    #   Almonds: this book's almond plots are placed in Alentejo, Portugal --
    #     a minor almond origin next to California's ~80% world share ->
    #     global_share ~1%; annual crop, modest carryover -> stock_to_use ~15%.
    "Olive oil":   {"global_share": 0.45, "stock_to_use": 25.0},
    "Durum wheat": {"global_share": 0.02, "stock_to_use": 32.0},
    "Citrus":      {"global_share": 0.03, "stock_to_use": 12.0},
    "Wine grapes": {"global_share": 0.01, "stock_to_use": 45.0},
    "Almonds":     {"global_share": 0.01, "stock_to_use": 15.0},

    # Cane sugar is NOT calibrated here: this book's cane-sugar plots are
    # placed in Valencia, Spain -- but Spain does not grow cane sugar at
    # commercial scale (its real sugar crop is sugar beet; cane sugar is
    # dominated by Brazil/India/Thailand). Assigning a "Spain's share of
    # world cane sugar" figure would be fabricating a number for a
    # geography that doesn't reflect real production -- left on
    # global_share=1.0 defaults instead, flagged here rather than papered
    # over with a confident-sounding but false calibration. The seed data's
    # placement itself looks like a demo-data mismatch worth revisiting.
}
_DEFAULT_PARAMS = {"sensitivity": None, "global_share": 1.0, "stock_to_use": None}

# Commodities whose impact function is calibrated to (and reproduces) a real event backtest.
# Everything else is flagged 'indicative' so unvalidated € is never blended with validated €.
BACKTESTED = {"Cocoa", "Coffee"}

# Commodities where real events show multiple same-season hazards on the SAME plot compound
# rather than substitute for each other -- Coffee's July 2021 event (drought weakened the
# trees, then frost delivered the damage on top of it: modeled worst-of alone reproduces only
# ~34% price move vs the real +44-60%; independent-multiplicative-damage combining reproduces
# ~49%, inside the real band, with NO other parameter changed -- see
# docs/SUPPLY_CHAIN_IMPACT_FUNCTION_METHODOLOGY.md §6.3). Opt-in per commodity, evidenced by a
# real backtest -- everything else keeps the default worst-of-single-hazard behavior, since
# most hazard pairs (e.g. flood vs wildfire) don't co-occur on the same plot/season at all.
COMPOUND_HAZARDS = {"Coffee"}


def _plot_severity(hazards: dict, compound: bool) -> float:
    """0-100 severity for one plot from its (possibly multiple) hazard scores --
    DISPLAY only (avg_hazard/top_hazard). Worst-of (default): the plot's single
    most severe hazard. Compounded (opt-in): independent multiplicative damage
    across the raw scores, 1 - product(1 - h/100). NOTE this is informational --
    the actual yield-shock calc uses _plot_yield_shock below, not this, because
    compounding RAW 0-100 scores saturates at 100 the instant any one hazard
    hits its own max (frost's threshold model hits 100 readily), discarding
    every other hazard's contribution regardless of severity."""
    if not compound or len(hazards) <= 1:
        return max(hazards.values())
    remaining = 1.0
    for score in hazards.values():
        remaining *= (1.0 - score / 100.0)
    return round((1.0 - remaining) * 100.0, 2)


def _plot_yield_shock(hazards: dict, sens: float, compound: bool) -> float:
    """0-1 local yield-shock fraction for one plot -- the actual §1.2 hazard-to-
    yield calc. Worst-of (default): sens x the single most severe hazard's
    score/100. Compounded (opt-in, COMPOUND_HAZARDS): independent multiplicative
    damage across each hazard's OWN sens-scaled yield-shock contribution --
    combining AFTER sensitivity, not on the raw 0-100 severity scores, so one
    hazard saturating at its own max (e.g. frost=100) doesn't erase a second,
    genuinely damaging hazard's contribution (e.g. drought=80)."""
    if not compound or len(hazards) <= 1:
        return sens * (max(hazards.values()) / 100.0)
    remaining = 1.0
    for score in hazards.values():
        remaining *= (1.0 - sens * (score / 100.0))
    return 1.0 - remaining


@dataclass
class CommodityRisk:
    commodity: str
    eudr_covered: bool
    annual_spend_eur: float
    n_plots: int
    n_plots_scored: int
    # 'scored'  — € published (every sourced origin is event-backtested)
    # 'pending' — no hazard score yet: exposure mapped, € withheld
    # 'held'    — scored, but the hazard→yield→price chain is NOT event-backtested for
    #             every sourced origin, so the € is withheld by the publish gate
    status: str
    # 'backtested' (every contributing origin event-validated) | 'mixed' (some origins
    # backtested, some not) | 'indicative' (none event-validated)
    calibration: str = "indicative"
    held_reason: Optional[str] = None
    hazard_combination: str = "worst_of"  # 'worst_of' (default) | 'compounded' (COMPOUND_HAZARDS)
    avg_hazard: Optional[float] = None
    top_hazard: Optional[str] = None
    yield_shock_pct: Optional[float] = None
    global_share: Optional[float] = None       # summed world share of the origins actually sourced
    global_shock_pct: Optional[float] = None   # Σ(origin yield shock × world share) — validated context
    # THE HEADLINE: yield_shock × spend. The volume the buyer paid for that will not arrive,
    # valued at the price they already pay. No forecast in it.
    volume_at_risk_eur: Optional[float] = None
    # The buyer's OWN price view, if they gave one. We never predict this — see _commodity_risk.
    price_scenario_pct: Optional[float] = None
    price_scenario_eur: Optional[float] = None
    # volume_at_risk_eur + price_scenario_eur (if the buyer supplied a view). No P90: the old
    # one was volume x 1.8, an invented "confidence band" with no distribution behind it. We do
    # not have a quantified uncertainty on the sensitivity yet, so we do not draw one.
    cogs_at_risk_p50: Optional[float] = None
    # 'ranged' tier: a driver explains the crop PARTLY, so the euro publishes as a band, not a
    # point. low = the optimistic end (least loss), high = the pessimistic end (most loss);
    # volume_at_risk_eur is the regression mid. fit_r2 is stated so the buyer sees the strength.
    # All None for a backtested point-estimate crop.
    volume_at_risk_low_eur: Optional[float] = None
    volume_at_risk_high_eur: Optional[float] = None
    fit_r2: Optional[float] = None
    # Composite Confidence Grade (A–E) — a transparent summary of how much to trust this crop's €,
    # built from out-of-sample r² + evidence depth + band calibration + proof type (ml.confidence_grade).
    # Sits ON TOP of the visible stats, never replaces them. None for held/pending (no published €).
    confidence_grade: Optional[str] = None
    confidence_checks: Optional[list] = None
    # Independent second-method (isotonic) cross-check of the champion fit — model-risk corroboration.
    challenger: Optional[dict] = None
    # Per-origin breakdown: which origin actually drives the world supply shock.
    origins: list = field(default_factory=list)
    override: Optional[dict] = None  # {model_p50_eur, override_p50_eur, overridden_by, overridden_at, reason} when set
    # What the yield labels physically count (olives-the-fruit, not oil). Metadata, not calc —
    # stamped from sc_commodities.measured_basis so the number is never read as something it
    # does not measure. See measured_basis_20260717.
    measured_basis: Optional[str] = None


@dataclass
class PortfolioCogsAtRisk:
    ingredient_spend_eur: float
    total_cogs_eur: float
    cogs_at_risk_p50: float          # volume at risk (+ the buyer's price scenario, if given)
    volume_at_risk_eur: float        # the physical half, always — no forecast in it
    pct_cogs_at_risk: float
    n_commodities: int
    n_pending: int
    # Held by the publish gate: scored, but not event-backtested → € withheld.
    # Reported as SPEND (a fact), never as a modelled €.
    n_held: int = 0
    held_spend_eur: float = 0.0
    covered_spend_eur: float = 0.0   # spend whose € IS published (backtested)
    commodities: list[CommodityRisk] = field(default_factory=list)
    impact_version: str = IMPACT_VERSION


def amplification(stock_to_use):
    """RETIRED — NOT ON ANY PUBLISHED PATH. Do not re-wire this into compute().

    Stock-to-use price amplification A(s) = (34.7/s)^3.62, fitted through two anchors, one of
    which (coffee at 40% stocks) turned out to be fabricated — the real figure is 14.2% (USDA
    PSD). Tested against a proper marketing-year panel it has no support: r^2 = 0.041, and the
    empirical exponent is 0.23 against our hardcoded 3.62. The relationship is not merely
    mis-fitted; it is not in the data, because price responds to what the market EXPECTS, not
    to measured stocks.

    It survives only so the research scripts that produced the historical price figures
    (backtest_storm/backtest_volcanic, build/fit_amplification_panel) still run and can still
    reproduce what we used to assert. compute() no longer calls it, and the published
    volume-at-risk is arithmetically independent of it and of stock_to_use — see
    tests/unit/test_price_chain_is_dead.py, which feeds the engine absurd stocks/elasticity
    and asserts the euro does not move.
    """
    if not stock_to_use:
        return TRANSMISSION
    return max(0.3, min(6.0, (34.7 / stock_to_use) ** 3.62))


def _fit_predict(fit: dict, score: float, z: float = 1.0) -> tuple:
    """(low, mid, high) climate anomaly % at a hazard score, from a stored 'ranged' regression.
    A real prediction interval: the band widens for a score far outside the training range.
    Mirrors ml.features.crop_fit.CropFit.predict — kept here so the engine has no ML import."""
    mid = fit["intercept"] + fit["slope"] * score
    se = fit["rmse"] * math.sqrt(1.0 + 1.0 / fit["n_years"]
                                 + ((score - fit["score_mean"]) ** 2) / fit["score_sxx"])
    return mid - z * se, mid, mid + z * se


def _ranged_plot_band(hazards: dict, fit: dict, driver: str) -> Optional[tuple]:
    """A plot's (best, mid, worst) LOSS fractions from the ranged fit at its driver score.
    Floored at 0 — a favourable year predicts a yield GAIN, which is not 'volume at risk'
    (upside is a separate model we deliberately do not fold into a risk number). Returns None
    when the driver hazard isn't scored on the plot."""
    score = hazards.get(driver)
    if score is None:
        return None
    lo, mid, hi = _fit_predict(fit, score)      # lo = most negative = worst loss
    return (max(0.0, -hi / 100.0), max(0.0, -mid / 100.0), max(0.0, -lo / 100.0))


def _driver_yield_shock(hazards: dict, sens: float, driver: str) -> Optional[float]:
    """Yield shock from ONLY the hazard the coefficient was backtested against.

    A calibrated sensitivity is not a general 'climate damage' number — it is the fitted
    response of one crop to ONE hazard (cocoa's 0.294 came from the 2023/24 HEAT event).
    Applying it to whatever hazard happens to score highest on a plot (wildfire, flood…)
    produces a figure no backtest supports. So for a calibrated origin we read the driver
    hazard only. Returns None when the driver hazard isn't scored on that plot — unknown,
    never silently 0 or substituted with another hazard."""
    score = hazards.get(driver)
    if score is None:
        return None
    return sens * (score / 100.0)


def _calibration_tier(name: str, origins: list) -> str:
    """A commodity's honesty label, derived from the ORIGINS this buyer actually sources —
    not from the commodity name. Coffee is 'backtested' for a Brazil-only book, but 'mixed'
    the moment Guatemala (never fitted to a Guatemalan event) is added, so validated and
    unvalidated € are never silently blended. Falls back to the legacy commodity-level
    BACKTESTED set when there is no per-origin calibration."""
    if not origins:
        return "backtested" if name in BACKTESTED else "indicative"
    # An origin only counts at its tier if it is BOTH calibrated at that tier AND actually
    # computable here — a coefficient whose driver hazard is unscored yields no number, so it
    # cannot back a published €. 'ranged' publishes too (as a band), but it is WEAKER than
    # backtested: a book mixing the two is labelled by the weakest publishable tier present.
    eff = set()
    for o in origins:
        t = o.get("calibration")
        if t in ("backtested", "ranged") and o.get("yield_shock_pct") is not None:
            eff.add(t)
        else:
            eff.add("indicative")
    if eff == {"backtested"}:
        return "backtested"
    if eff <= {"backtested", "ranged"}:          # every origin publishable, at least one ranged
        return "ranged"
    if eff & {"backtested", "ranged"}:           # some publishable, some not → do not blend
        return "mixed"
    return "indicative"


def _commodity_risk(name, eudr, spend, plots, sens, global_share,
                    compound=False, origin_cal=None, price_scenario_pct=None) -> CommodityRisk:
    """plots: list of dicts {spend, origin, hazards:{hz→score}} (scored plots carry hazards).

    `elasticity` and `amp` used to sit in this signature and were never read in the body — the
    published figure is physical (yield_shock x spend) and cannot depend on them. Dead
    parameters that still look alive are an invitation to re-wire the retired price chain, so
    they are gone rather than merely unused.
    compound: see COMPOUND_HAZARDS -- worst-of by default, independent-multiplicative-damage
    for commodities with real backtest evidence hazards stack rather than substitute.

    origin_cal: {origin → {sensitivity, world_share, calibration_tier, hazard_driver}} from
    sc_commodity_calibration. When present the WORLD supply shock is summed per origin:
        global_shock = Σ_origins( origin_yield_shock × origin_world_share )
    which is the physically correct chain -- each origin contributes in proportion to its share
    of world PRODUCTION, not to how much this buyer happens to source there. When absent we keep
    the legacy single-bucket behaviour (one yield shock × one global_share) unchanged."""
    scored = [p for p in plots if p.get("hazards")]
    n_plots, n_scored = len(plots), len(scored)
    if n_scored == 0:
        # exposure mapped, € pending (governance §8)
        return CommodityRisk(name, eudr, spend, n_plots, 0, status="pending")

    # spend-weighted plot severity (display) and yield-shock (sourcing channel) across plots
    wsum = sum(p["spend"] for p in scored) or 1.0
    avg_hazard = sum(_plot_severity(p["hazards"], compound) * p["spend"] for p in scored) / wsum
    top_hazard = max(
        ((hz, sc) for p in scored for hz, sc in p["hazards"].items()),
        key=lambda t: t[1],
    )[0]
    # A cell can now carry several hazards (e.g. BOTH drought and soil_water since the
    # water-availability layer). For a CALIBRATED crop, the hazard we display must be the one
    # that actually drives its € — its calibrated driver — not whichever raw score is highest.
    # Olive is drought-driven even where its cells also carry a higher soil_water score.
    _drivers = {(origin_cal or {}).get(p.get("origin"), {}).get("hazard_driver") for p in scored}
    _drivers.discard(None)
    if len(_drivers) == 1:
        _d = next(iter(_drivers))
        if any(_d in p.get("hazards", {}) for p in scored):
            top_hazard = _d
    # The buyer's OWN exposure — spend-weighted over their plots. Each plot is read with ITS
    # OWN ORIGIN'S calibrated sensitivity and driver hazard, not a commodity-wide constant.
    # BUG THIS FIXES (found by test, 2026-07-16): this used the commodity-level `sens` from the
    # code's COMMODITY_PARAMS (cocoa 0.294), silently shadowing the DB calibration that was
    # re-fitted on real data (0.1995). The per-origin world-shock path already used the right
    # value, so the two halves of the same object disagreed — and once volume-at-risk became
    # THE headline, the headline was the one using the stale number.
    def _plot_shock(p):
        cal = (origin_cal or {}).get(p.get("origin")) if origin_cal else None
        if cal:
            driver = cal.get("hazard_driver")
            fit = cal.get("fit")
            if fit and driver:
                # ranged: the buyer's loss is the regression MID at the plot's driver score
                band = _ranged_plot_band(p["hazards"], fit, driver)
                return band[1] if band is not None else 0.0
            o_sens = cal.get("sensitivity") or sens
            if driver:
                v = _driver_yield_shock(p["hazards"], o_sens, driver)
                return v if v is not None else 0.0
            return _plot_yield_shock(p["hazards"], o_sens, compound)
        return _plot_yield_shock(p["hazards"], sens, compound)

    yield_shock = sum(_plot_shock(p) * p["spend"] for p in scored) / wsum   # §1.2 hazard → yield shock

    origins: list[dict] = []
    if origin_cal:
        # §1.3 per-ORIGIN: world shock = Σ (origin yield shock × origin world share)
        # Group ALL plots, not just the scored ones. An origin whose plots are entirely
        # unscored must still SURFACE as a gap — if it silently vanished from the breakdown,
        # the commodity would look fully validated on whatever origins happen to be scored
        # while half the buyer's spend (and its share of the world crop) went unrepresented.
        global_shock = 0.0
        by_origin: dict = {}
        for p in plots:
            by_origin.setdefault(p.get("origin"), []).append(p)
        for origin, oplots in sorted(by_origin.items(), key=lambda kv: str(kv[0])):
            cal = origin_cal.get(origin)
            o_sens = (cal or {}).get("sensitivity") or sens
            o_share = (cal or {}).get("world_share")
            driver = (cal or {}).get("hazard_driver")
            o_fit = (cal or {}).get("fit")
            o_spend = sum(p["spend"] for p in oplots) or 1.0

            need = None
            if driver:
                # Calibrated origin: only the backtested/fitted hazard may drive the yield shock.
                scored_on_driver = [p for p in oplots if p.get("hazards", {}).get(driver) is not None]
                if scored_on_driver:
                    w = sum(p["spend"] for p in scored_on_driver) or 1.0
                    if o_fit:
                        # ranged: regression MID loss at each plot's driver score
                        o_shock = sum(_ranged_plot_band(p["hazards"], o_fit, driver)[1] * p["spend"]
                                      for p in scored_on_driver) / w
                    else:
                        o_shock = sum(_driver_yield_shock(p["hazards"], o_sens, driver) * p["spend"]
                                      for p in scored_on_driver) / w
                else:
                    o_shock = None
                    need = f"{driver} not scored on these plots — the calibrated driver hazard"
            else:
                # No validated hazard DRIVER for this origin, so no validated yield shock —
                # exposure only. Name exactly what is missing: if we already know the origin's
                # world share, don't wrongly claim it's absent.
                o_shock = None
                need = ("a validated hazard driver for this origin"
                        if o_share is not None
                        else "world production share + a validated hazard driver for this origin")

            contribution = (o_shock * o_share) if (o_shock is not None and o_share is not None) else None
            if contribution is not None:
                global_shock += contribution
            origins.append({
                "origin": origin, "spend_eur": round(o_spend, 2),
                "yield_shock_pct": round(o_shock * 100, 1) if o_shock is not None else None,
                "world_share": o_share,
                "global_shock_contribution_pct": round(contribution * 100, 2) if contribution is not None else None,
                "calibration": (cal or {}).get("calibration_tier", "uncalibrated"),
                "hazard_driver": driver,
                # An origin with no calibration row cannot contribute to the world price signal —
                # surfaced, never silently given another origin's share or another hazard's score.
                "input_required": need,
            })
    else:
        global_shock = yield_shock * global_share                   # legacy single-bucket

    # ── THE HEADLINE: volume at risk. Physical, and the half we can actually prove. ──
    # The buyer's own plots lose `yield_shock` of their yield, so that share of the volume
    # they paid for does not arrive. Valued at the price they ALREADY pay — no forecast of
    # any kind enters this number. It is the direct euro consequence of the crop failure our
    # hazard chain predicts, and that chain is validated against the real event (cocoa's
    # modelled world shock 8.92% vs FAO's measured 8.88%).
    volume_at_risk = yield_shock * spend

    # ── Ranged band: when the driver explains the crop PARTLY, publish a range, not a point. ──
    # Spend-weight each scored plot's (best, worst) loss from the stored regression's prediction
    # interval; the mid already equals yield_shock above. floored at 0 — a favourable year is a
    # gain, not "volume at risk". fit_r2 is surfaced so the buyer sees the strength of the fit.
    vol_low_eur = vol_high_eur = fit_r2 = None
    ranged = [(p, (origin_cal or {}).get(p.get("origin"), {}).get("fit"),
               (origin_cal or {}).get(p.get("origin"), {}).get("hazard_driver"))
              for p in scored] if origin_cal else []
    ranged = [(p, f, d) for (p, f, d) in ranged if f and d
              and _ranged_plot_band(p["hazards"], f, d) is not None]
    if ranged:
        wr = sum(p["spend"] for p, _, _ in ranged) or 1.0
        best = sum(_ranged_plot_band(p["hazards"], f, d)[0] * p["spend"] for p, f, d in ranged) / wr
        worst = sum(_ranged_plot_band(p["hazards"], f, d)[2] * p["spend"] for p, f, d in ranged) / wr
        vol_low_eur = round(best * spend, 2)
        vol_high_eur = round(worst * spend, 2)
        # Display the OUT-OF-SAMPLE r² (the honest, cross-validated number the publish gate uses),
        # not the optimistic in-sample r². Keeps the held-reason ("explains X% of bad years, below
        # our 40% bar") coherent with what actually gates publication. (audit F2)
        fit_r2 = round(max((f["r2_oos"] if f.get("r2_oos") is not None else 0.0) for _, f, _ in ranged), 4)

    # ── The price channel: the customer's assumption, never our prediction. ──
    # We tested "supply shock -> price move" on 440 real crop-years: r^2 = 0.018. A harvest
    # failure does push price up (64% of 53 real contractions) but HOW MUCH is unpredictable
    # from supply data — by the time production is measured the market priced the news months
    # ago. So we do not forecast it. If the buyer supplies their own price view (they trade
    # this daily; we do not), we apply it to their whole spend and label it as theirs.
    price_scenario = (price_scenario_pct / 100.0) * spend if price_scenario_pct else None
    p50 = volume_at_risk + (price_scenario or 0.0)

    return CommodityRisk(
        commodity=name, eudr_covered=eudr, annual_spend_eur=spend,
        n_plots=n_plots, n_plots_scored=n_scored, status="scored",
        hazard_combination="compounded" if compound else "worst_of",
        avg_hazard=round(avg_hazard, 1), top_hazard=top_hazard,
        yield_shock_pct=round(yield_shock * 100, 1),
        global_share=(round(sum(o["world_share"] for o in origins if o["world_share"] is not None), 5)
                      if origins else global_share),
        # World shock stays: it is validated and it is real context ("the world crop is down
        # 8.9%"). It just no longer drives a price prediction.
        global_shock_pct=round(global_shock * 100, 2),
        volume_at_risk_eur=round(volume_at_risk, 2),
        volume_at_risk_low_eur=vol_low_eur,
        volume_at_risk_high_eur=vol_high_eur,
        fit_r2=fit_r2,
        price_scenario_pct=price_scenario_pct,
        price_scenario_eur=round(price_scenario, 2) if price_scenario is not None else None,
        cogs_at_risk_p50=round(p50, 2),
        origins=origins,
    )


def compute(commodities: list[dict], total_cogs_eur: float, overrides: Optional[dict] = None,
            calibrations: Optional[dict] = None, publish_gate: bool = True,
            price_scenario_pct: Optional[float] = None) -> PortfolioCogsAtRisk:
    """
    Pure roll-up. `commodities` = list of
      {name, eudr_covered, elasticity, spend, plots:[{spend, origin, hazards:{hz:score}}]}.

    calibrations: optional {commodity_name: {origin: {sensitivity, world_share,
    calibration_tier, hazard_driver}}} from sc_commodity_calibration. When a commodity has
    calibration rows, its world supply shock is summed PER ORIGIN (each origin contributing in
    proportion to its share of world production). Without them the commodity keeps the legacy
    single-bucket behaviour off COMMODITY_PARAMS, so pure-function callers are unaffected.

    overrides: optional {commodity_name: {override_cogs_at_risk_p50_eur, overridden_by,
    overridden_at, reason}} -- a procurement analyst's audited correction to a SCORED
    commodity's model figure (see sc_commodity_overrides migration). p90 is re-derived
    from the override at the same P90_FACTOR the model itself uses, for a consistent range.

    publish_gate: when True (the default, and the customer-facing contract) a commodity's €
    is published ONLY if every origin it sources is event-backtested; otherwise it is 'held'
    (exposure + hazard driver shown, € withheld). Set False only for internal calibration
    work -- never for output a customer or a disclosure sees.
    """
    overrides = overrides or {}
    calibrations = calibrations or {}
    risks: list[CommodityRisk] = []
    for c in commodities:
        p = {**_DEFAULT_PARAMS, **COMMODITY_PARAMS.get(c["name"], {})}
        origin_cal = calibrations.get(c["name"])
        # No elasticity / stock_to_use / amplification read here any more: they fed the price
        # move, which is retired. `elasticity` and `stock_to_use` stay on the input dict and in
        # the DB because the research panel still uses them -- they simply reach nothing that
        # publishes.
        sens = p["sensitivity"] if p["sensitivity"] is not None else CROP_SENSITIVITY.get(c["name"], DEFAULT_SENSITIVITY)
        cr = _commodity_risk(c["name"], c["eudr_covered"], c["spend"], c["plots"],
                             sens, p["global_share"],
                             compound=c["name"] in COMPOUND_HAZARDS,
                             origin_cal=origin_cal,
                             price_scenario_pct=price_scenario_pct)
        cr.calibration = _calibration_tier(c["name"], cr.origins)
        cr.measured_basis = c.get("measured_basis")

        # Confidence Grade — computed for a PUBLISHED crop from its stored, auditable validation
        # stats (out-of-sample r² + band calibration for ranged; event-reproduction for backtested).
        if origin_cal and cr.calibration in ("backtested", "ranged"):
            _cal_any = next((v for v in origin_cal.values()
                             if (cr.calibration == "ranged" and v.get("fit"))
                             or (cr.calibration == "backtested" and v.get("backtest"))), None)
            if _cal_any is not None:
                if cr.calibration == "ranged":
                    _f = _cal_any["fit"]
                    _chal = _cal_any.get("challenger")
                    _g = _grade(tier="ranged", r2_oos=_f.get("r2_oos"),
                                n_years=_f.get("n_years"), band_cov68=_f.get("band_cov68"),
                                corroboration=(_chal.get("verdict") if _chal else None))
                    cr.challenger = _chal
                else:
                    _b = _cal_any["backtest"]
                    _g = _grade(tier="backtested", reproduction_err_pct=_b.get("repro_err_pct"),
                                n_events=_b.get("n_events"))
                cr.confidence_grade = _g.grade
                cr.confidence_checks = _g.checks

        # ── PUBLISH GATE (governance §8, hard rule) ──────────────────────────
        # A euro figure leaves this engine ONLY if the hazard→yield→price chain has
        # been reproduced against a real, documented event for EVERY origin the buyer
        # sources. Anything else keeps its exposure and its hazard driver, but the €
        # is withheld — never shown behind a disclaimer, because a number on a page
        # gets used no matter what the banner says.
        # 'ranged' publishes too (as a band, r² stated) — it is a fitted, evidenced tier, just
        # weaker than a single-event backtest. Only 'mixed'/'indicative' stay held.
        if publish_gate and cr.status == "scored" and cr.calibration not in ("backtested", "ranged"):
            gaps = [f"{o['origin']}: {o['input_required']}" for o in cr.origins if o.get("input_required")]
            unvalidated = [str(o["origin"]) for o in cr.origins
                           if o.get("calibration") not in ("backtested", "ranged") and not o.get("input_required")]
            cr.status = "held"
            # A crop with no per-origin calibration rows (legacy path) has no origins to list —
            # give it a clean, specific reason rather than a dangling "€ withheld —".
            if not unvalidated and not gaps and cr.fit_r2 is None:
                reason = ("€ withheld — exposure mapped; the hazard→yield chain is not yet "
                          "validated for this crop, so no € is published.")
            else:
                reason = "€ withheld — "
                if unvalidated:
                    reason += "hazard→yield not event-backtested for " + ", ".join(unvalidated) + ". "
                if gaps:
                    reason += "missing input — " + "; ".join(gaps) + ". "
            # If we actually FITTED this crop but it fell below the publish floor, say so — that
            # is a stronger, more honest signal than "not validated". fit_r2 survives on the
            # object (set in the ranged block); we keep it precisely so the reason can be specific.
            if cr.fit_r2 is not None:
                # truncate (not round) the crop's share so a 0.397 fit reads "39%", clearly
                # UNDER the 40% bar, rather than rounding up to a misleading "40%".
                reason = (f"€ withheld — {cr.top_hazard or 'driver'} tested: explains "
                          f"{int(cr.fit_r2 * 100)}% of bad years, below our "
                          f"{round(RANGED_PUBLISH_FLOOR * 100)}% bar to publish. Exposure mapped.")
            cr.held_reason = reason.strip() or (
                "€ withheld until the chain reproduces a real crop failure")
            # Withhold every modelled economic claim, INCLUDING the ranged band — a held crop
            # publishes no €. Keep the measured exposure and fit_r2 (the reason we withheld).
            cr.cogs_at_risk_p50 = cr.volume_at_risk_eur = None
            cr.volume_at_risk_low_eur = cr.volume_at_risk_high_eur = None
            cr.price_scenario_eur = cr.global_shock_pct = None

        ov = overrides.get(c["name"])
        if ov and cr.status == "scored":
            model_p50 = cr.cogs_at_risk_p50
            cr.cogs_at_risk_p50 = round(ov["override_cogs_at_risk_p50_eur"], 2)
            cr.override = {
                "model_p50_eur": model_p50, "override_p50_eur": cr.cogs_at_risk_p50,
                "overridden_by": ov.get("overridden_by"), "overridden_at": ov.get("overridden_at"),
                "reason": ov.get("reason"),
            }
        risks.append(cr)

    # Only PUBLISHED (backtested) commodities contribute €. Held/pending exposure is
    # reported as SPEND, never rolled into the headline — an un-backtested € must not
    # reach a total that someone then acts on.
    scored = [r for r in risks if r.status == "scored"]
    held = [r for r in risks if r.status == "held"]
    p50 = sum(r.cogs_at_risk_p50 for r in scored)
    vol = sum(r.volume_at_risk_eur or 0 for r in scored)
    spend = sum(r.annual_spend_eur for r in risks)
    risks.sort(key=lambda r: (r.cogs_at_risk_p50 or -1), reverse=True)
    return PortfolioCogsAtRisk(
        ingredient_spend_eur=round(spend, 2),
        total_cogs_eur=round(total_cogs_eur, 2),
        cogs_at_risk_p50=round(p50, 2),
        volume_at_risk_eur=round(vol, 2),
        pct_cogs_at_risk=round(100 * p50 / total_cogs_eur, 2) if total_cogs_eur else 0.0,
        n_commodities=len(risks),
        n_pending=len([r for r in risks if r.status == "pending"]),
        n_held=len(held),
        held_spend_eur=round(sum(r.annual_spend_eur for r in held), 2),
        covered_spend_eur=round(sum(r.annual_spend_eur for r in scored), 2),
        commodities=risks,
    )


# ── DB adapter ───────────────────────────────────────────────────────────────

_GRAPH_SQL = """
    SELECT co.name AS commodity, co.eudr_covered, co.demand_elasticity AS elasticity,
           co.stock_to_use, co.measured_basis, p.country AS origin,
           p.plot_id::text AS plot_id, p.annual_spend_eur AS plot_spend,
           v.hazard_type, v.physical_risk_score
    FROM   sc_sourcing_plots p
    JOIN   sc_commodities   co ON co.commodity_id = p.commodity_id
    LEFT   JOIN v_sc_plot_physical_risk v
           ON v.plot_id = p.plot_id AND v.scenario = :scenario AND v.time_horizon = :horizon
    WHERE  p.org_id = :org_id
"""


def get_calibrations(session) -> dict:
    """Per-origin calibration keyed {commodity_name: {origin: params}} — compute()'s shape.

    Reads v_sc_commodity_calibration, NOT the base table. calibration_tier is DERIVED there
    from sc_model_validation: a crop×origin is 'backtested' if and only if a validation row
    exists that PASSED, on the same hazard the coefficient drives. It is not a column anyone
    can type — you cannot write your way to a published euro (see crop_registry_20260715).

    Not org-scoped: an origin's share of world production and its validated hazard driver are
    facts about the world, not about a tenant."""
    from sqlalchemy import text
    rows = session.execute(text("""
        SELECT co.name AS commodity, c.origin,
               CAST(c.sensitivity AS FLOAT) AS sensitivity,
               CAST(c.world_share AS FLOAT) AS world_share,
               c.hazard_driver, c.calibration_tier, c.event_ref, c.source_note
        FROM v_sc_commodity_calibration c
        JOIN sc_commodities co ON co.commodity_id = c.commodity_id
    """)).mappings().all()
    out: dict = {}
    for r in rows:
        out.setdefault(r["commodity"], {})[r["origin"]] = dict(r)

    # Attach the regression behind a 'ranged' origin so the engine can emit a BAND rather than a
    # point. Keyed the same {commodity: {origin: ...}}; only ranged origins carry a 'fit'.
    fits = session.execute(text("""
        SELECT co.name AS commodity, f.origin, f.hazard_driver,
               CAST(f.slope AS FLOAT) AS slope, CAST(f.intercept AS FLOAT) AS intercept,
               CAST(f.rmse AS FLOAT) AS rmse, CAST(f.r2 AS FLOAT) AS r2,
               CAST(f.score_mean AS FLOAT) AS score_mean, CAST(f.score_sxx AS FLOAT) AS score_sxx,
               f.n_years, CAST(f.r2_oos AS FLOAT) AS r2_oos, CAST(f.band_cov68 AS FLOAT) AS band_cov68
        FROM sc_commodity_fit f JOIN sc_commodities co ON co.commodity_id = f.commodity_id
    """)).mappings().all()
    for f in fits:
        origin = out.get(f["commodity"], {}).get(f["origin"])
        if origin is not None and origin.get("hazard_driver") == f["hazard_driver"]:
            origin["fit"] = dict(f)

    # Backtest reproduction stats per origin — the Confidence Grade inputs for a backtested crop:
    # how close the model reproduced the real event, and how many events back it.
    for b in session.execute(text("""
        SELECT co.name AS commodity, v.origin,
               count(*) AS n_events,
               min(abs(CAST(v.model_prod_shock_pct AS FLOAT) - CAST(v.observed_prod_shock_pct AS FLOAT))
                   / NULLIF(abs(CAST(v.observed_prod_shock_pct AS FLOAT)),0) * 100) AS repro_err_pct
        FROM sc_model_validation v JOIN sc_commodities co ON co.commodity_id = v.commodity_id
        WHERE v.passed AND v.model_prod_shock_pct IS NOT NULL AND v.observed_prod_shock_pct IS NOT NULL
        GROUP BY co.name, v.origin
    """)).mappings().all():
        origin = out.get(b["commodity"], {}).get(b["origin"])
        if origin is not None:
            origin["backtest"] = {"n_events": b["n_events"],
                                  "repro_err_pct": float(b["repro_err_pct"]) if b["repro_err_pct"] is not None else None}

    # Independent challenger verdict per ranged origin — the model-risk corroboration (a 2nd method,
    # isotonic, cross-checking the champion OLS on the same panel). See ml/features/challenger.py.
    for ch in session.execute(text("""
        SELECT co.name AS commodity, x.origin, x.hazard_driver, x.method, x.n_years, x.verdict,
               CAST(x.mean_abs_divergence_pp AS FLOAT) AS mean_abs_divergence_pp,
               CAST(x.tolerance_pp AS FLOAT) AS tolerance_pp, CAST(x.ref_score AS FLOAT) AS ref_score,
               CAST(x.champion_at_ref_pct AS FLOAT) AS champion_at_ref_pct,
               CAST(x.challenger_at_ref_pct AS FLOAT) AS challenger_at_ref_pct, x.challenger_version
        FROM sc_commodity_challenger x JOIN sc_commodities co ON co.commodity_id = x.commodity_id
    """)).mappings().all():
        origin = out.get(ch["commodity"], {}).get(ch["origin"])
        if origin is not None and origin.get("hazard_driver") == ch["hazard_driver"]:
            origin["challenger"] = dict(ch)
    return out


def get_commodity_overrides(session, org_id: str) -> dict:
    """This org's active commodity overrides, keyed by commodity NAME (compute()'s key),
    not commodity_id -- sc_commodities is a small shared reference table."""
    from sqlalchemy import text
    rows = session.execute(text("""
        SELECT co.name AS commodity, CAST(o.override_cogs_at_risk_p50_eur AS FLOAT) AS override_cogs_at_risk_p50_eur,
               o.overridden_by::text AS overridden_by, o.overridden_at, o.reason
        FROM sc_commodity_overrides o JOIN sc_commodities co ON co.commodity_id = o.commodity_id
        WHERE o.org_id = :o
    """), {"o": org_id}).mappings().all()
    return {r["commodity"]: dict(r) for r in rows}


def apply_commodity_override(session, org_id: str, commodity_id: str, override_p50_eur: float,
                              user_id: str, reason: Optional[str]) -> dict:
    from datetime import datetime, timezone
    from sqlalchemy import text
    now = datetime.now(timezone.utc)
    session.execute(text("""
        INSERT INTO sc_commodity_overrides (org_id, commodity_id, override_cogs_at_risk_p50_eur, overridden_by, overridden_at, reason)
        VALUES (:o, :c, :p, :u, :now, :reason)
        ON CONFLICT (org_id, commodity_id) DO UPDATE
            SET override_cogs_at_risk_p50_eur = EXCLUDED.override_cogs_at_risk_p50_eur,
                overridden_by = EXCLUDED.overridden_by, overridden_at = EXCLUDED.overridden_at,
                reason = EXCLUDED.reason
    """), {"o": org_id, "c": commodity_id, "p": override_p50_eur, "u": user_id, "now": now, "reason": reason})
    return {"overridden_at": now}


def clear_commodity_override(session, org_id: str, commodity_id: str) -> bool:
    from sqlalchemy import text
    result = session.execute(text(
        "DELETE FROM sc_commodity_overrides WHERE org_id = :o AND commodity_id = :c"
    ), {"o": org_id, "c": commodity_id})
    return result.rowcount > 0


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
            "stock_to_use": float(r["stock_to_use"]) if r["stock_to_use"] is not None else None,
            "measured_basis": r["measured_basis"],
            "spend": 0.0, "_plots": {},
        })
        pl = c["_plots"].setdefault(r["plot_id"], {
            "spend": float(r["plot_spend"] or 0), "origin": r["origin"], "hazards": {},
        })
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
    overrides = get_commodity_overrides(session, org_id)
    return compute(commodities, float(total_cogs), overrides, calibrations=get_calibrations(session))
