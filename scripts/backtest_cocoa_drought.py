"""
Native hazard→yield backtest (first half): is the 2023/24 cocoa collapse a genuine
climate outlier in the real West-Africa data? Computes the cocoa-belt SPEI-3 / SPI-3 /
temperature anomaly per year from the ERA5-Land baseline, ranks each year against the
1991–2024 distribution, and cross-references the crop_yield_observations production shock.

This is the link scripts/backtest_supply_impact.py could NOT test (no native scores then).
Run: .venv/bin/python scripts/backtest_cocoa_drought.py
"""
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from ml.features.drought import load_monthly, compute_indices, seasonal_by_year

NC = "data/era5_baseline/west_africa_cocoa_1991_2024_monthly.nc"
# cocoa main-crop development / harvest window in West Africa (annual perennial stress)
SEASON = list(range(1, 13))


def pct_rank(value, series):
    s = np.array([v for v in series if v is not None])
    return round(100.0 * (s < value).sum() / len(s), 0)


def main():
    idx = compute_indices(load_monthly(NC), scale=3)
    years = seasonal_by_year(idx, SEASON)
    by_year = {y["year"]: y for y in years}
    spei_series = [y["spei"] for y in years]
    temp_series = [y["temp_anom_c"] for y in years]

    # production labels (YoY) from ground truth
    with get_session() as s:
        prod = {r["season_year"]: r for r in s.execute(text("""
            SELECT season_year, production_tonnes, yoy_change_pct
            FROM crop_yield_observations WHERE commodity='cocoa' AND country='WLD'
            ORDER BY season_year
        """)).mappings().all()}

    print("=" * 74)
    print("NATIVE COCOA DROUGHT/HEAT BACKTEST — West Africa cocoa belt, 1991–2024")
    print("=" * 74)
    print("Driest years by SPEI-3 (most negative = most water-stressed):")
    for y in sorted(years, key=lambda z: z["spei"])[:6]:
        print(f"   {y['year']}  SPEI {y['spei']:+.2f}   temp anom {y['temp_anom_c']:+.2f}°C   precip deficit {y['precip_deficit_mm']:+.0f}mm")
    print("Hottest years by temperature anomaly:")
    for y in sorted(years, key=lambda z: -z["temp_anom_c"])[:6]:
        print(f"   {y['year']}  temp anom {y['temp_anom_c']:+.2f}°C   SPEI {y['spei']:+.2f}")

    print("\n--- The 2023/24 season vs the 34-year record ---")
    for yr in (2023, 2024):
        y = by_year.get(yr)
        if not y:
            continue
        print(f"  {yr}: SPEI {y['spei']:+.2f} (drier than {100-pct_rank(y['spei'], spei_series):.0f}% of years), "
              f"temp anom {y['temp_anom_c']:+.2f}°C (hotter than {pct_rank(y['temp_anom_c'], temp_series):.0f}% of years)")

    print("\n--- Climate signal vs observed production (ground truth) ---")
    print("  season  world cocoa YoY   belt SPEI   belt temp anom")
    for yr in sorted(prod):
        p = prod[yr]; y = by_year.get(yr, {})
        yoy = f"{float(p['yoy_change_pct']):+5.1f}%" if p["yoy_change_pct"] is not None else "   —  "
        print(f"   {yr}     {yoy}        {y.get('spei','  —'):>5}      {y.get('temp_anom_c','  —'):>5}°C")

    print("\nVERDICT: if 2023/24 is an extreme hot/dry outlier AND aligns with the −12.9%")
    print("production drop, the drought/heat hazard signal is real for this event (climate")
    print("share; disease/EUDR/speculation still contribute — see methodology §4).")


if __name__ == "__main__":
    main()
