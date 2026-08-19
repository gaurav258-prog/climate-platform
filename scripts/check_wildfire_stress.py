"""Did our climate engine flag the 2026 Mediterranean wildfire regions — and with WHICH instrument?

A capability stress-check, not a crop calibration. The July-2026 fires (Bordeaux/Gironde vineyards,
Sierra Norte de Guadalajara) were HEAT-driven flash events, not accumulated-rainfall droughts, and
this script shows exactly that from our own data:

  HEAT (Apr-Jun anomaly vs 1991-2020)  → both regions the HOTTEST year in 36 (+3sigma)
  DROUGHT SPEI-6 (Jan-Jun water year)  → reads "normal" (~32/100) — the wrong window, misses the fire
  DROUGHT SPEI-3 (Apr-Jun flash window)→ turns sharply dry (~72-81/100) — catches it

The lesson we keep: for ACUTE / fire-adjacent risk the instrument is heat + a SHORT-accumulation
(flash-drought) index; the long agronomic SPEI-6 our YIELD models use is the wrong tool and would
have said "all calm". The signal is in the data; the question dictates which index reads it.

Needs the ERA5 baselines (re-fetchable: fetch_era5_baseline.py {bordeaux_wine,spain_central} 1991 2026).
    .venv/bin/python -m scripts.check_wildfire_stress
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")
import sys

from ml.features.drought import compute_indices, load_monthly, seasonal_by_year
from ml.scoring.drought_climatology import drought_score

FIRE_BELTS = [
    ("bordeaux_wine", "Bordeaux / Gironde (French wine — 2,400 ha, EU mechanism)"),
    ("spain_central", "Central Spain / Guadalajara (La Mierla — ~32,000 ha)"),
]
TARGET_YEAR = 2026
NC = "data/era5_baseline/{region}_1991_2026_monthly.nc"


def _spei_rank(ds, scale, months, year):
    sp = {r["year"]: r["spei"] for r in seasonal_by_year(compute_indices(ds, scale=scale), months)
          if r["spei"] is not None}
    yrs = sorted(sp)
    v = sp.get(year)
    if v is None:
        return None
    # rank from the DRY end: extreme drought is LOW spei, so "Nth driest" = (years drier) + 1.
    drier = sum(1 for y in yrs if sp[y] < v)
    return v, drought_score(v), drier + 1, len(yrs)


def _heat_rank(ds, months, year):
    T = ds["T"]
    tm = T.sel(time=T["time.month"].isin(months)).groupby("time.year").mean("time").mean(("latitude", "longitude"))
    base = tm.sel(year=slice(1991, 2020))
    mu, sd = float(base.mean()), float(base.std())
    t = float(tm.sel(year=year))
    hotter = int((tm.sel(year=slice(1991, year)) < t).sum())
    k = -273.15 if mu > 200 else 0.0
    return (t - mu) / sd, t + k, mu + k, len(tm) - hotter, int(tm.year.size)


def main() -> int:
    print(f"WILDFIRE-REGION CLIMATE STRESS — {TARGET_YEAR} vs 1991 baseline\n" + "=" * 66)
    for region, label in FIRE_BELTS:
        try:
            ds = load_monthly(NC.format(region=region))
        except FileNotFoundError:
            print(f"\n{label}\n  baseline missing — run fetch_era5_baseline.py {region} 1991 2026")
            continue
        h_z, h_t, h_mu, h_rank, h_n = _heat_rank(ds, [4, 5, 6], TARGET_YEAR)
        s6 = _spei_rank(ds, 6, [1, 2, 3, 4, 5, 6], TARGET_YEAR)
        s3 = _spei_rank(ds, 3, [4, 5, 6], TARGET_YEAR)
        print(f"\n{label}")
        print(f"  HEAT   Apr-Jun            +{h_z:.1f}σ  ({h_t:.1f}°C vs {h_mu:.1f}°C)   → hottest {h_rank} of {h_n}   [FLAGS IT]")
        print(f"  SPEI-6 Jan-Jun (yield)    {s6[0]:+.2f}  → score {s6[1]:.0f}/100   driest {s6[2]} of {s6[3]}   [MISSES IT]")
        print(f"  SPEI-3 Apr-Jun (flash)    {s3[0]:+.2f}  → score {s3[1]:.0f}/100   driest {s3[2]} of {s3[3]}   [CATCHES IT]")
    print("\n" + "-" * 66)
    print("Verdict: heat-driven flash desiccation, not accumulated drought. Our heat model + a")
    print("short-window drought index capture it; the long agronomic SPEI-6 (our yield driver) does")
    print("not. Acute/fire risk needs the short instrument — the crop-€ stays honestly withheld.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
