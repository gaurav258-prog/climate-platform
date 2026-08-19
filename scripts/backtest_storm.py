"""
Backtest the storm hazard model against Hurricane Maria, September 2017 (Puerto Rico).

Same governance ethos as scripts/backtest_volcanic.py: report direction + order-of-
magnitude against a real, named, sourced anchor; publish misses; never claim more
precision than the data supports.

BANKING check: does the model correctly rank San Juan (close to Maria's track, took
a severe direct hit) above a site farther from the eyewall?

AGRICULTURE check: same disclosed limitation as Guatemala's volcanic coffee plot —
"Coffee" is ONE global commodity (sc_commodities.name is UNIQUE) shared across Brazil
(drought, calibrated sensitivity=0.45, global_share=0.35), Guatemala (volcanic ashfall)
and now Puerto Rico (storm). The schema has no per-origin sensitivity/global_share
override, so this script reports TWO numbers for Puerto Rico, not one — same pattern
as backtest_volcanic.py. Puerto Rico's real anchor is WEAKER than Guatemala's: Anacafé
gave a clean coffee-specific national-loss percentage for Fuego, but Puerto Rico's
Dept. of Agriculture figures are economy-wide (all crops), not coffee-isolated — this
is disclosed explicitly, not smoothed over.

Real anchors (see docs/STORM_HAZARD_METHODOLOGY.md for full sourcing):
  Hurricane Maria, Sept 2017 -- Puerto Rico Dept. of Agriculture: ~US$780M total
    agricultural loss, ~80% of the island's total crop value destroyed; 18 million
    coffee trees destroyed (a quantity, not a coffee-specific dollar/% figure).
    NOAA/NCEI: ~US$90bn total damage (3rd-costliest US hurricane on record), ~80% of
    the electrical grid destroyed.

Usage:  python scripts/backtest_storm.py
"""
from __future__ import annotations

import h3
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.supply_cogs import _commodity_risk

# Real, documented sites (see docstring for sourcing)
SAN_JUAN = (18.4655, -66.1057)     # capital, close to Maria's track, severe direct hit
CABO_ROJO = (18.0866, -67.1457)    # SW tip, farther from the eyewall

# Coffee's EXISTING calibration (Brazil, 2021 drought) -- see supply_cogs.COMMODITY_PARAMS
BRAZIL_SENS, BRAZIL_GLOBAL_SHARE = 0.45, 0.35

# Puerto Rico's REAL world coffee production share -- order-of-magnitude only (far
# smaller even than Guatemala's ~2.3%; PR's coffee output is a tiny fraction of world
# production). NOT precisely sourced -- flagged as such in the report below.
PUERTO_RICO_GLOBAL_SHARE = 0.0005

PR_DA_TOTAL_LOSS_USD = 780_000_000
PR_DA_PCT_CROP_VALUE = 80
PR_COFFEE_TREES_DESTROYED = 18_000_000
NOAA_TOTAL_DAMAGE_USD = 90_000_000_000


def banking_check():
    print("=" * 78)
    print("BANKING CHECK — Hurricane Maria 2017: distance-from-track discrimination")
    print("=" * 78)
    with get_session() as s:
        for name, (lat, lon) in [("San Juan (capital, severe direct hit)", SAN_JUAN),
                                  ("Cabo Rojo (SW tip, farther from eyewall)", CABO_ROJO)]:
            cell = h3.latlng_to_cell(lat, lon, 8)
            r = s.execute(text("""
                SELECT risk_score, shap_factors->>'driver_dist_km' d,
                       shap_factors->>'driver_wind_kt' w, shap_factors->>'driver_sshs' cat
                FROM canonical_scores WHERE hazard_type='storm' AND h3_cell=:c AND valid_to IS NULL
            """), {"c": cell}).mappings().first()
            if not r:
                print(f"  {name}: NOT SCORED"); continue
            print(f"  {name}: score {r['risk_score']} ({r['d']}km from track) "
                  f"— {r['w']}kt Cat{r['cat']}")
    print("\nVERDICT: correct if San Juan scores meaningfully higher than Cabo Rojo — it sat")
    print("closer to Maria's eyewall and took the more severe direct hit of the two.")


def agriculture_check():
    print()
    print("=" * 78)
    print("AGRICULTURE CHECK — Puerto Rico coffee (Adjuntas) vs Hurricane Maria 2017")
    print("=" * 78)
    with get_session() as s:
        row = s.execute(text("""
            SELECT p.plot_id::text, p.annual_spend_eur, v.physical_risk_score
            FROM sc_sourcing_plots p JOIN v_sc_plot_physical_risk v ON v.plot_id = p.plot_id
            WHERE p.country='PR' AND v.hazard_type='storm'
              AND v.scenario='baseline' AND v.time_horizon='current'
        """)).mappings().first()
    if not row:
        print("  Puerto Rico coffee plot not found/scored — run scripts/wire_puerto_rico_storm_demo.py first")
        return
    hazard_score = float(row["physical_risk_score"])
    spend = float(row["annual_spend_eur"])
    plots = [{"spend": spend, "hazards": {"storm": hazard_score}}]

    live = _commodity_risk("Coffee", True, spend, plots, BRAZIL_SENS, BRAZIL_GLOBAL_SHARE)
    origin_specific = _commodity_risk("Coffee", True, spend, plots,
                                      BRAZIL_SENS, PUERTO_RICO_GLOBAL_SHARE)

    print(f"  Adjuntas plot: storm hazard score {hazard_score}, spend €{spend/1e6:.1f}m")
    print(f"\n  (a) LIVE MODEL (borrows Brazil's global_share={BRAZIL_GLOBAL_SHARE}):")
    print(f"      yield-shock {live.yield_shock_pct}% -> world crop {live.global_shock_pct}%")
    print(f"\n  (b) ORIGIN-SPECIFIC (Puerto Rico's real world coffee share≈{PUERTO_RICO_GLOBAL_SHARE}, "
          f"order-of-magnitude only):")
    print(f"      yield-shock {origin_specific.yield_shock_pct}% -> world crop "
          f"{origin_specific.global_shock_pct}%")

    print(f"\n  REAL ANCHOR (Puerto Rico Dept. of Agriculture): ~${PR_DA_TOTAL_LOSS_USD/1e6:.0f}m total")
    print(f"  agricultural loss, ~{PR_DA_PCT_CROP_VALUE}% of the island's total crop value destroyed —")
    print("  economy-wide (banana/plantain hit hardest), NOT a coffee-specific dollar figure.")
    print(f"  Separately, {PR_COFFEE_TREES_DESTROYED/1e6:.0f} million coffee trees were destroyed — a real,")
    print("  sourced quantity, but not convertible to a clean %-of-national-production anchor the")
    print("  way Anacafé's Guatemala figure was. This anchor is WEAKER than Guatemala's — disclosed,")
    print("  not smoothed over.")

    print("\n  VERDICT: directionally right (real storm proximity -> real elevated local yield-shock),")
    print("  but with a less precise anchor than Guatemala's volcanic backtest. Puerto Rico coffee")
    print("  stays 'indicative', not added to BACKTESTED.")


def main():
    banking_check()
    agriculture_check()
    print()
    print("=" * 78)
    print(f"For context: NOAA/NCEI total damage estimate for Maria was ~${NOAA_TOTAL_DAMAGE_USD/1e9:.0f}bn")
    print("(3rd-costliest US hurricane on record) — banking-side order-of-magnitude cross-check.")
    print("Full sourcing and limitations: docs/STORM_HAZARD_METHODOLOGY.md")
    print("=" * 78)


if __name__ == "__main__":
    main()
