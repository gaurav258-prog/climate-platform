"""
Insurance underwriting — "expected loss and premium from the score" (the
Loss-curve pricing service catalog.js has advertised since the catalog was
first written, previously a workflow=null placeholder with nothing behind it).

Three steps, each grounded in a named, citable convention rather than
invented from scratch:

1. Risk score -> Mean Damage Ratio (MDR): the fraction of insured value lost
   IF the location's worst on-record hazard scenario recurs. Uses the
   sigmoid impact-function form popularised by Emanuel (2011) for tropical-
   cyclone wind damage and now the default vulnerability-curve shape in
   CLIMADA (ETH Zurich's open-source climate risk model): MDD(v) = v^3 /
   (1 + v^3), where v=1 is the "half-damage point" (MDD=0.5) and MDD -> 1 as
   v grows. CLIMADA fits v from a physical hazard intensity (e.g. wind
   speed) calibrated per peril; this platform's canonical risk_score is
   already a cross-hazard 0-100 severity currency (see every hazard's
   score_to_bucket), so v = score / HALF_DAMAGE_SCORE substitutes for it
   directly. HALF_DAMAGE_SCORE=65 reuses score_to_bucket's existing
   High/Very-High boundary as the half-damage anchor rather than fitting a
   new one with no loss data to fit against.

   sum_insured * MDR is a SCENARIO loss (a Probable-Maximum-Loss-style
   figure: "what this policy loses if its worst-known event recurs"), NOT
   yet an annual expected loss -- most of this platform's risk_scores are
   themselves severity-of-worst-known-event numbers (e.g. seismic's worst
   nearby M>=5 quake, storm's worst nearby track), not annual probabilities.
   Conflating the two would silently inflate premiums (a "High" score would
   imply a >=50% ANNUAL loss rate, which is not what "High severity, IF it
   happens" means) -- caught by sanity-checking a first draft of this module
   against realistic real-world cat-insurance rate-on-line figures before
   shipping it, not assumed correct on the first pass.

2. Scenario loss -> Expected Annual Loss (EAL) via an annual occurrence
   probability, using the same return-period tiers real flood/wind risk
   mapping already standardises on (e.g. FEMA's 100-year floodplain, ASCE-7
   wind-hazard return periods) -- RETURN_PERIOD_YEARS below maps this
   platform's own L/M/H/VH buckets to a 1-in-200 / 1-in-50 / 1-in-20 /
   1-in-10-year assumption. **Disclosed simplification**: a real return
   period would be fitted per hazard/location from an event catalog (this
   platform doesn't have one yet for most hazards); a flat per-bucket tier
   is a stated placeholder, not a claim of fitted frequency data.

   OPT-IN alternative (org_calc_settings.insurance_return_period_model =
   'peril_specific'): PERIL_RETURN_PERIOD_YEARS varies the tier by which
   hazard actually drove the bucket -- a seismic/volcanic VH event is
   genuinely rarer-but-more-catastrophic than a flood/wildfire/storm VH event
   at the same location (consistent with real building-code return periods,
   e.g. ASCE-7 seismic design at ~475yr vs FEMA's 100yr flood standard), and
   chronic perils (drought/heat/pollution) recur more often than acute
   catastrophe perils. Same disclosure standard as the fixed table: illustrative
   relative tiers, NOT fitted per-location frequency data. Every org gets the
   fixed table unless it explicitly opts in -- see services/calc_settings.py.

3. Expected Annual Loss -> premium via the Casualty Actuarial Society's
   loss-cost-multiplier ratemaking method: Gross Premium = Pure Premium /
   (1 - expense_ratio - profit_margin), where Pure Premium = Expected Annual
   Loss (CAS Statement of Principles Regarding P&C Ratemaking, Principle 2).
   EXPENSE_RATIO=0.25 / PROFIT_MARGIN=0.05 are disclosed, round assumptions
   consistent with typical P&C combined-ratio targets (~70-75% loss ratio),
   not a fitted or sourced figure for any real insurer.

Deductible: `deductible_pct` was captured on every policy upload from day one
(a fraction of sum insured, e.g. 0.02 = 2%) but never reached this pricing
chain -- a real field, silently unused. Standard per-occurrence property
treatment: the insured retains losses up to the deductible layer, so the
insurer's scenario loss is netted down by that retained amount before EAL/
premium are derived from it (floored at zero -- a small scenario loss fully
inside the deductible costs nothing to insure).
"""
from __future__ import annotations

from core.types import score_to_bucket
from ml.scoring.damage_function import HALF_DAMAGE_SCORE, vulnerability_factor  # noqa: F401
from ml.scoring.damage_function import mean_damage_ratio as _core_mdr

EXPENSE_RATIO = 0.25
PROFIT_MARGIN = 0.05

# Bucket -> assumed annual occurrence probability of the scored worst-case
# scenario recurring (1/return-period-years). See module docstring, step 2.
RETURN_PERIOD_YEARS = {"L": 200, "M": 50, "H": 20, "VH": 10}

PERIL_RETURN_PERIOD_YEARS = {
    "seismic":       {"L": 1000, "M": 475, "H": 250, "VH": 100},
    "volcanic":      {"L": 1000, "M": 475, "H": 250, "VH": 100},
    "flood":         {"L": 250,  "M": 100, "H": 50,  "VH": 25},
    "wildfire":      {"L": 200,  "M": 75,  "H": 30,  "VH": 12},
    "storm":         {"L": 200,  "M": 60,  "H": 25,  "VH": 12},
    "drought":       {"L": 100,  "M": 40,  "H": 15,  "VH": 7},
    "heat_acute":    {"L": 100,  "M": 40,  "H": 15,  "VH": 7},
    "heat_chronic":  {"L": 100,  "M": 40,  "H": 15,  "VH": 7},
    "pollution":     {"L": 100,  "M": 40,  "H": 15,  "VH": 7},
}


def mean_damage_ratio(risk_score: float, hazard: str | None = None, attrs: dict | None = None) -> float:
    """Emanuel(2011)/CLIMADA sigmoid — now vulnerability-aware via the shared damage core
    (ml/scoring/damage_function.py). With no attrs it is the bare sigmoid, unchanged: 0 at score=0,
    0.5 at HALF_DAMAGE_SCORE, asymptotic to 1.0 for very severe scores."""
    return _core_mdr(risk_score, hazard, attrs)


def price_policy(risk_score: float, sum_insured_eur: float, deductible_pct: float = 0.0,
                  hazard: str | None = None, return_period_model: str = "fixed",
                  attrs: dict | None = None, expense_ratio: float = EXPENSE_RATIO,
                  profit_margin: float = PROFIT_MARGIN) -> dict:
    """Returns {mdr, scenario_loss_eur, retained_loss_eur, net_scenario_loss_eur,
    annual_occurrence_prob, expected_annual_loss_eur, pure_premium_eur,
    gross_premium_eur, rate_on_line_pct, risk_bucket} — the full "score ->
    scenario loss -> deductible-netted loss -> annualized loss -> premium"
    chain, everything traceable back to the single risk_score input.
    deductible_pct: fraction of sum_insured retained by the insured (e.g. 0.02
    = 2%), same units as the upload template's deductible_pct column.
    hazard/return_period_model: pass the driving hazard + the org's chosen
    insurance_return_period_model (services/calc_settings.py) to price a
    seismic VH policy's frequency differently from a flood VH policy; omit
    either to get today's fixed L/M/H/VH tier, unchanged."""
    bucket = score_to_bucket(risk_score).value
    mdr = mean_damage_ratio(risk_score, hazard, attrs)
    vf, vf_prov = vulnerability_factor(hazard, attrs)
    scenario_loss = sum_insured_eur * mdr
    retained_loss = sum_insured_eur * max(0.0, deductible_pct or 0.0)
    net_scenario_loss = max(0.0, scenario_loss - retained_loss)
    if return_period_model == "peril_specific" and hazard in PERIL_RETURN_PERIOD_YEARS:
        return_period = PERIL_RETURN_PERIOD_YEARS[hazard].get(bucket, RETURN_PERIOD_YEARS["L"])
    else:
        return_period = RETURN_PERIOD_YEARS.get(bucket, RETURN_PERIOD_YEARS["L"])
    annual_prob = 1.0 / return_period
    eal = net_scenario_loss * annual_prob
    # loadings are institution interpretation switches (services/calc_settings.py); guard against a
    # degenerate 100% load. Default reproduces the shipped 0.25 / 0.05.
    loaded = max(0.05, 1.0 - (expense_ratio or 0.0) - (profit_margin or 0.0))
    gross_premium = eal / loaded
    return {
        "mdr": round(mdr, 4),
        "scenario_loss_eur": round(scenario_loss, 2),
        "retained_loss_eur": round(retained_loss, 2),
        "net_scenario_loss_eur": round(net_scenario_loss, 2),
        "return_period_years": return_period,
        "return_period_model": return_period_model,
        "annual_occurrence_prob": annual_prob,
        "expected_annual_loss_eur": round(eal, 2),
        "pure_premium_eur": round(eal, 2),
        "gross_premium_eur": round(gross_premium, 2),
        "rate_on_line_pct": round(100 * gross_premium / sum_insured_eur, 3) if sum_insured_eur else 0.0,
        "risk_bucket": bucket,
        # the building-attribute vulnerability multiplier the mdr already carries, surfaced so the
        # premium's differentiation from a same-score neutral building is disclosed, not silent.
        "vulnerability_factor": vf,
        "vulnerability": vf_prov,
    }
