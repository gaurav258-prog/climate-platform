"""
Backtest the volcanic hazard model against two real eruptions: Fuego 2018
(Guatemala, primary -- dual banking+agriculture case) and Taal 2020
(Philippines, secondary -- cleaner ashfall-only generalisation test).

Same governance ethos as scripts/backtest_cocoa_drought.py / backtest_coffee_climate.py:
report direction + order-of-magnitude against a real, named, sourced anchor;
publish misses; never claim more precision than the data supports.

BANKING check: does the model correctly separate proximal-destruction sites
(San Miguel Los Lotes, destroyed by PDC) from ashfall-only sites (Antigua)?

AGRICULTURE check: this is the harder one, and its limitation is disclosed
rather than hidden. "Coffee" is ONE global commodity (sc_commodities.name is
UNIQUE) shared across Brazil (drought, calibrated sensitivity=0.45,
global_share=0.35) and Guatemala (volcanic ashfall, added on top). The schema
has no per-origin sensitivity/global_share override, so this script reports
TWO numbers for Guatemala, not one:
  (a) what the LIVE product actually computes if Guatemala's hazard is priced
      using Brazil's shared calibration (global_share=0.35 -- Brazil's world
      share, not Guatemala's) -- i.e. what a user of the product sees today.
  (b) what a properly origin-specific calculation implies using GUATEMALA'S
      OWN much-smaller world coffee share (~2.3%, ICO/USDA order-of-magnitude),
      which is the fairer comparison against the real Fuego/Anacafé anchor.
(a) is expected to overstate Guatemala's global price impact (it borrows
Brazil's 15x-larger world share) -- that mismatch is the point of computing
both, not an error to hide.

Real anchors (see docs/VOLCANIC_HAZARD_METHODOLOGY.md for full sourcing):
  Fuego 2018  -- MAGA (Guatemala's agriculture ministry): ~US$12.3M total
                 agricultural loss, 13,611 ha, corn/vegetables/fruit dominant.
                 Anacafé (national coffee association): ~8.5M lbs green coffee
                 lost, ~0.9% of national production -- coffee-specific, but a
                 NATIONAL average diluted across origins far from Fuego.
  Taal 2020   -- Philippine DA: PHP 3.06bn total agricultural damage,
                 15,790 ha; coffee = 10.9% of that ≈ PHP 333.5M (~US$6.5M).

Usage:  python scripts/backtest_volcanic.py
"""
from __future__ import annotations

import h3
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.supply_cogs import _commodity_risk

# Real, documented sites (see docstring for sourcing)
SAN_MIGUEL_LOS_LOTES = (14.4180, -90.8590)   # destroyed by PDC, June 3 2018
ANTIGUA_GUATEMALA = (14.5586, -90.7295)       # ashfall only, not destroyed

# Coffee's EXISTING calibration (Brazil, 2021 drought) -- see supply_cogs.COMMODITY_PARAMS
BRAZIL_SENS, BRAZIL_GLOBAL_SHARE = 0.45, 0.35

# Guatemala's REAL world coffee production share -- order-of-magnitude from
# ICO/USDA (roughly 3.5-4M 60kg bags/yr vs ~170M bags world total), NOT fit to
# this event. Distinct from Brazil's 0.35 used in the live shared commodity.
GUATEMALA_GLOBAL_SHARE = 0.023

FUEGO_MAGA_LOSS_USD = 12_300_000
FUEGO_MAGA_HA = 13_611
FUEGO_ANACAFE_PCT_NATIONAL_PRODUCTION = 0.9  # %, Anacafé's own projection
TAAL_DA_TOTAL_PHP = 3_060_000_000
TAAL_DA_COFFEE_SHARE_PCT = 10.9


def banking_check():
    print("=" * 78)
    print("BANKING CHECK — Fuego 2018: proximal destruction vs ashfall-only sites")
    print("=" * 78)
    with get_session() as s:
        for name, (lat, lon) in [("San Miguel Los Lotes (destroyed by PDC)", SAN_MIGUEL_LOS_LOTES),
                                  ("Antigua Guatemala (ashfall only)", ANTIGUA_GUATEMALA)]:
            cell = h3.latlng_to_cell(lat, lon, 8)
            r = s.execute(text("""
                SELECT risk_score, shap_factors->>'driver_dist_km' d,
                       shap_factors->>'proximal_score' p, shap_factors->>'ashfall_score' a
                FROM canonical_scores WHERE hazard_type='volcanic' AND h3_cell=:c AND valid_to IS NULL
            """), {"c": cell}).mappings().first()
            if not r:
                print(f"  {name}: NOT SCORED"); continue
            driver = "PROXIMAL" if float(r["p"]) >= float(r["a"]) else "ashfall"
            print(f"  {name}: score {r['risk_score']} ({r['d']}km from vent) "
                  f"— proximal {r['p']} / ashfall {r['a']} → driven by {driver}")
    print("\nVERDICT: correct if Los Lotes is proximal-driven (it was destroyed by a")
    print("pyroclastic flow, not buried in ash) and Antigua is ashfall-driven/lower (it")
    print("received ashfall but was not in the PDC's path).")


def agriculture_check():
    print()
    print("=" * 78)
    print("AGRICULTURE CHECK — Guatemala coffee (Alotenango/Antigua) vs Fuego 2018")
    print("=" * 78)
    with get_session() as s:
        row = s.execute(text("""
            SELECT p.plot_id::text, p.annual_spend_eur, v.physical_risk_score
            FROM sc_sourcing_plots p JOIN v_sc_plot_physical_risk v ON v.plot_id = p.plot_id
            WHERE p.country='GT' AND v.hazard_type='volcanic'
              AND v.scenario='baseline' AND v.time_horizon='current'
        """)).mappings().first()
    if not row:
        print("  Guatemala coffee plot not found/scored — run scripts/wire_guatemala_volcanic_demo.py first")
        return
    hazard_score = float(row["physical_risk_score"])
    spend = float(row["annual_spend_eur"])
    plots = [{"spend": spend, "hazards": {"volcanic": hazard_score}}]

    # (a) what the LIVE shared-commodity model actually computes (Brazil's calibration
    #     applied to Guatemala's hazard, isolated to just this plot's spend)
    live = _commodity_risk("Coffee", True, spend, plots, BRAZIL_SENS, BRAZIL_GLOBAL_SHARE)
    # (b) origin-specific: same hazard->yield sensitivity, Guatemala's OWN world share
    origin_specific = _commodity_risk("Coffee", True, spend, plots,
                                      BRAZIL_SENS, GUATEMALA_GLOBAL_SHARE)

    print(f"  Alotenango plot: volcanic hazard score {hazard_score}, spend €{spend/1e6:.1f}m")
    print(f"\n  (a) LIVE MODEL (borrows Brazil's global_share={BRAZIL_GLOBAL_SHARE} -- what the")
    print(f"      product shows today, since Coffee is one shared commodity):")
    print(f"      yield-shock {live.yield_shock_pct}% -> world crop {live.global_shock_pct}%")
    print(f"\n  (b) ORIGIN-SPECIFIC (Guatemala's real world coffee share={GUATEMALA_GLOBAL_SHARE}, "
          f"the fairer comparison):")
    print(f"      yield-shock {origin_specific.yield_shock_pct}% -> world crop "
          f"{origin_specific.global_shock_pct}%")

    print(f"\n  REAL ANCHOR (Anacafé): ~{FUEGO_ANACAFE_PCT_NATIONAL_PRODUCTION}% of Guatemala's NATIONAL")
    print(f"  coffee production lost -- a country-wide average diluted across origins far from")
    print(f"  Fuego, not a local Antigua-only figure. Local yield-shock at plots actually near")
    print(f"  Fuego should be HIGHER than the national average (same dilution logic as cocoa's")
    print(f"  world-share discussion in the methodology doc).")
    print(f"\n  REAL ANCHOR (MAGA): ~${FUEGO_MAGA_LOSS_USD/1e6:.1f}m total agricultural loss across")
    print(f"  {FUEGO_MAGA_HA:,} ha (corn/vegetables/fruit dominant, coffee a minor share of this --")
    print(f"  not a coffee-only figure, cross-check on ORDER OF MAGNITUDE only).")

    print(f"\n  VERDICT: model-(b)'s local yield-shock ({origin_specific.yield_shock_pct}%) is the")
    print(f"  right kind of number to compare against a LOCAL Antigua-region loss estimate, which")
    print(f"  we do not have (Anacafé's 0.9% is national). Order-of-magnitude only, NOT a precise")
    print(f"  match -- disclosed, not claimed. This is why Guatemala's plot stays 'indicative',")
    print(f"  not added as a second BACKTESTED origin under Coffee.")


def taal_secondary_check():
    print()
    print("=" * 78)
    print("SECONDARY (generalisation test, not wired into any demo plot) — Taal 2020")
    print("=" * 78)
    coffee_php = TAAL_DA_TOTAL_PHP * TAAL_DA_COFFEE_SHARE_PCT / 100
    print(f"  Philippine DA: PHP {TAAL_DA_TOTAL_PHP/1e9:.2f}bn total agricultural damage,")
    print(f"  coffee = {TAAL_DA_COFFEE_SHARE_PCT}% of that = PHP {coffee_php/1e6:.1f}m "
          f"(~US${coffee_php/51/1e6:.1f}m at ~51 PHP/USD, Jan 2020).")
    print("  Not wired into a demo plot (Taal's crop mix is vegetables/banana-dominant, not")
    print("  coffee-dominant) -- kept as a documented secondary target, direction-only.")


def main():
    banking_check()
    agriculture_check()
    taal_secondary_check()
    print()
    print("=" * 78)
    print("Full sourcing and the shared-commodity limitation discussion:")
    print("docs/VOLCANIC_HAZARD_METHODOLOGY.md")
    print("=" * 78)


if __name__ == "__main__":
    main()
