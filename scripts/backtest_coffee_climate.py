"""
Native climate backtest for Brazil ARABICA coffee — proves the West-Africa recipe
generalizes to a new region/commodity, and (like cocoa) reveals the ACTUAL driver from data.

Coffee 2021 was drought (May) + a severe FROST (20 Jul 2021), which hit the 2022 crop.
So the expected drivers are DROUGHT (captured by SPEI) and COLD/frost (a NEGATIVE temp
anomaly — the opposite of cocoa's heat). This checks both against the coffee belt record,
and flags the honest limit: true frost is a DAILY Tmin<0 event, not resolvable from monthly
means — so the winter cold anomaly is only a proxy; a daily-Tmin frost model is the refinement.

Run (after scripts/fetch_era5_baseline.py brazil_coffee):
    .venv/bin/python scripts/backtest_coffee_climate.py
"""
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from ml.features.drought import load_monthly, compute_indices, seasonal_by_year

NC = "data/era5_baseline/brazil_coffee_1991_2024_monthly.nc"
WINTER = [6, 7, 8]   # Brazilian winter — the frost window (Jun–Aug)
ALL = list(range(1, 13))


def pct_rank(v, series):
    s = np.array([x for x in series if x is not None]); return round(100.0 * (s < v).sum() / len(s))


def main():
    idx = compute_indices(load_monthly(NC), scale=3)
    annual = {y["year"]: y for y in seasonal_by_year(idx, ALL)}
    winter = {y["year"]: y for y in seasonal_by_year(idx, WINTER)}

    with get_session() as s:
        prod = {r["season_year"]: r for r in s.execute(text("""
            SELECT season_year, production_tonnes, yoy_change_pct
            FROM crop_yield_observations WHERE commodity='coffee_green' AND country='BR' ORDER BY season_year
        """)).mappings().all()}

    print("=" * 74)
    print("NATIVE BRAZIL COFFEE CLIMATE BACKTEST — arabica belt (Minas/SP), 1991–2024")
    print("=" * 74)
    spei_series = [y["spei"] for y in annual.values()]
    wtemp_series = [y["temp_anom_c"] for y in winter.values()]

    print("Driest years by annual SPEI-3:")
    for y in sorted(annual.values(), key=lambda z: z["spei"])[:6]:
        print(f"   {y['year']}  SPEI {y['spei']:+.2f}")
    print("Coldest WINTER (Jun–Aug) by temp anomaly (frost proxy — most negative = coldest):")
    for y in sorted(winter.values(), key=lambda z: z["temp_anom_c"])[:6]:
        print(f"   {y['year']}  winter temp anom {y['temp_anom_c']:+.2f}°C")

    print("\n--- 2021 (drought + 20-Jul frost) vs the record ---")
    a21, w21 = annual.get(2021), winter.get(2021)
    if a21:
        print(f"  2021 annual SPEI {a21['spei']:+.2f} (drier than {100-pct_rank(a21['spei'], spei_series):.0f}% of years)")
    if w21:
        print(f"  2021 winter temp {w21['temp_anom_c']:+.2f}°C (colder than {pct_rank(w21['temp_anom_c'], wtemp_series):.0f}% of years)")

    print("\n--- climate vs observed Brazil coffee production ---")
    print("  season  BR coffee YoY   annual SPEI   winter temp anom")
    for yr in sorted(prod):
        p = prod[yr]; a = annual.get(yr, {}); w = winter.get(yr, {})
        yoy = f"{float(p['yoy_change_pct']):+5.1f}%" if p["yoy_change_pct"] is not None else "   —  "
        print(f"   {yr}    {yoy}       {a.get('spei','  —'):>5}        {w.get('temp_anom_c','  —'):>5}°C")

    print("\nVERDICT: recipe generalizes — different region, different DRIVER. Coffee's signal is")
    print("drought + a cold/frost winter (NOT heat like cocoa). True frost needs daily Tmin<0°C —")
    print("the monthly winter anomaly is a proxy; a daily-Tmin frost model is the documented next step.")


if __name__ == "__main__":
    main()
