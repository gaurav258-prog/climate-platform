"""Identify WHICH hazard actually drives a crop's failures, from data — never from intuition.

WHY. A calibrated coefficient is only valid for the hazard it was fitted against, so picking
the wrong driver silently produces confident nonsense. Intuition has been wrong every single
time we have checked:
  * cocoa 2023/24 tracked EXTREME HEAT, not drought — 2023 was the WETTEST year on record
    (SPEI +2.15); attributing cocoa to drought would have been flatly wrong.
  * coffee 2021 was DROUGHT, not heat (and the July frost is invisible in monthly means).
So we test candidates against the data and let the correlation decide.

METHOD. For a (commodity, origin):
  1. take the crop's CLIMATE-ATTRIBUTABLE anomaly per year (ml/features/crop_cycle — the raw
     YoY would just measure the tree's alternate-bearing cycle, not the weather);
  2. take each candidate hazard index per year for the crop's region and season window
     (SPEI/SPI = drought, temperature anomaly = heat), from the ERA5 baseline;
  3. correlate. The driver is the index that actually explains the crop's bad years.
Sign matters and is asserted: drought must correlate POSITIVELY with production (drier =
lower SPEI = worse crop), heat NEGATIVELY (hotter = worse crop). A "strong" correlation with
the wrong sign is a red flag, not a driver.

    python -m scripts.identify_crop_driver --commodity "Olive oil" --origin ES \
        --region spain_olive --season 4,5,6,7,8 --source "EUROSTAT apro_cpsh1"
"""
from __future__ import annotations

import argparse
import math
import sys

from sqlalchemy import text

from core.db.session import get_session
from ml.features.crop_cycle import decompose
from ml.features.drought import compute_indices, load_monthly, seasonal_by_year

NC_TEMPLATE = "data/era5_baseline/{region}_1991_2024_monthly.nc"


def _pearson(xs: list, ys: list) -> float:
    n = len(xs)
    if n < 6:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return (num / (dx * dy)) if dx and dy else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commodity", required=True)
    ap.add_argument("--origin", required=True)
    ap.add_argument("--region", required=True, help="regions.py key with an ERA5 baseline")
    ap.add_argument("--season", required=True, help="comma-separated months, e.g. 4,5,6,7,8")
    ap.add_argument("--source", default="EUROSTAT apro_cpsh1")
    ap.add_argument("--event-year", type=int)
    args = ap.parse_args()

    months = [int(m) for m in args.season.split(",")]

    # 1. the crop's climate-attributable anomaly per year (cycle + trend removed)
    with get_session() as s:
        rows = s.execute(text("""
            SELECT season_year, production_tonnes FROM crop_yield_observations
            WHERE commodity = :c AND country = :o AND source = :s AND production_tonnes > 0
        """), {"c": args.commodity, "o": args.origin, "s": args.source}).fetchall()
    series = {int(a): float(b) for a, b in rows}
    if len(series) < 12:
        print(f"only {len(series)} usable years — cannot identify a driver")
        return 1
    dec = decompose(series)
    print(f"{args.commodity}/{args.origin}: {dec['n_years']} yrs {dec['span']}, "
          f"phi={dec['phi']} alternate_bearing={dec['alternate_bearing']}")

    # 2. candidate hazard indices per year for this region+season
    ds = load_monthly(NC_TEMPLATE.format(region=args.region))
    idx = compute_indices(ds)
    seasonal = {r["year"]: r for r in seasonal_by_year(idx, months)}

    # 3. correlate on the years both sides have, using only calibratable (non-edge) years
    common = sorted(set(series) & set(seasonal))
    usable = [y for y in common if dec["years"][y]["trend_full_window"]]
    print(f"overlap {len(common)} yrs, {len(usable)} usable (non-edge): "
          f"{usable[0] if usable else '-'}..{usable[-1] if usable else '-'}\n")
    if len(usable) < 8:
        print("too few usable overlapping years to identify a driver")
        return 1

    crop = [dec["years"][y]["climate_pct"] for y in usable]
    CANDIDATES = {
        "drought (SPEI)":  ("spei",        +1, "drier (low SPEI) => worse crop"),
        "drought (SPI)":   ("spi",         +1, "drier (low SPI) => worse crop"),
        "heat (T anom)":   ("temp_anom_c", -1, "hotter => worse crop"),
    }
    print(f"{'candidate':18s} {'r':>7s} {'expected sign':>14s}  verdict")
    print("-" * 74)
    best = None
    for label, (key, expect, why) in CANDIDATES.items():
        hz = [seasonal[y][key] for y in usable]
        r = _pearson(hz, crop)
        right_sign = (r > 0) if expect > 0 else (r < 0)
        verdict = ("DRIVER" if abs(r) >= 0.45 and right_sign
                   else "wrong sign" if abs(r) >= 0.45 else "weak")
        print(f"{label:18s} {r:>7.3f} {('+' if expect > 0 else '-'):>14s}  {verdict:11s} {why}")
        if verdict == "DRIVER" and (best is None or abs(r) > abs(best[1])):
            best = (label, r, key)

    print()
    if best:
        print(f"=> driver: {best[0]}  (r={best[1]:.3f})")
    else:
        print("=> NO driver identified: no candidate is both strong and correctly signed. "
              "This crop/origin cannot be calibrated on these indices — say so rather than "
              "picking the least-bad one.")

    if args.event_year:
        ey = dec["years"].get(args.event_year)
        sy = seasonal.get(args.event_year)
        if ey and sy:
            print(f"\nevent {args.event_year}: crop climate anomaly {ey['climate_pct']}% "
                  f"(raw {ey['raw_yoy_pct']}%), SPEI {sy['spei']}, SPI {sy['spi']}, "
                  f"T anom {sy['temp_anom_c']}C, usable={ey['trend_full_window']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
