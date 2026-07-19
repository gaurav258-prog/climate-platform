"""Does BASIN RESERVOIR STORAGE explain an irrigated crop better than rainfall (SPEI)?

The honest test of the irrigation-water hypothesis. Meteorological drought (SPEI) and soil moisture
see the SKY; they do not see the RESERVOIR a farmer actually irrigates from. For heavily-irrigated
Iberian crops (sugar beet in the Duero, citrus in the Jucar/Segura) the mediating variable is basin
storage. We decompose the crop's yield into its climate-attributable anomaly, build a per-year
reservoir-fill index for the crop's demarcation(s) over its water-demand window, and regress. It
wins only if it explains MORE than SPEI over the same years — never assumed. Leave-one-out CV r2
reported too, because in-sample r2 on ~25-37 points overstates.

    python -m scripts.compare_reservoir_driver --commodity "Sugar beet" --origin ES \
        --source "FAOSTAT QCL bulk" --basins Duero --season 6,7,8,9 --region spain_beet
"""
from __future__ import annotations
import argparse, csv, sys
from collections import defaultdict
from statistics import mean, pstdev

from sqlalchemy import text
from core.db.session import get_session
from ml.features.crop_cycle import decompose

IDX = "data/reservoirs/basin_reservoir_index.csv"


def reservoir_seasonal(basins, months):
    """Per year: mean fill ratio across the given basins over the season months, then z-scored."""
    per = defaultdict(list)  # year -> [fill,...]
    with open(IDX, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["basin"] in basins and int(r["month"]) in months:
                per[int(r["year"])].append(float(r["fill_ratio"]))
    raw = {y: mean(v) for y, v in per.items() if v}
    mu, sd = mean(raw.values()), pstdev(raw.values())
    return {y: (v - mu) / sd for y, v in raw.items()} if sd else {}


def ols1(xs, ys):
    n = len(ys)
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if not sxx:
        return 0.0, 0.0, 0.0
    b = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / sxx
    a = my - b * mx
    yh = [a + b * x for x in xs]
    sst = sum((y - my) ** 2 for y in ys)
    ssr = sum((ys[i] - yh[i]) ** 2 for i in range(n))
    r2 = 1 - ssr / sst if sst else 0.0
    # leave-one-out CV
    loo = 0.0
    for i in range(n):
        idx = [j for j in range(n) if j != i]
        mxx, myy = mean([xs[j] for j in idx]), mean([ys[j] for j in idx])
        sx = sum((xs[j] - mxx) ** 2 for j in idx)
        if not sx:
            return r2, 0.0, b
        bb = sum((xs[j] - mxx) * (ys[j] - myy) for j in idx) / sx
        aa = myy - bb * mxx
        loo += (ys[i] - (aa + bb * xs[i])) ** 2
    loo_r2 = 1 - loo / sst if sst else 0.0
    return r2, loo_r2, b


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commodity", required=True)
    ap.add_argument("--origin", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--basins", required=True, help="comma-sep AMBITO names")
    ap.add_argument("--season", default="6,7,8,9")
    args = ap.parse_args()
    basins = set(args.basins.split("|"))
    months = [int(m) for m in args.season.split(",")]

    res = reservoir_seasonal(basins, months)
    with get_session() as s:
        rows = s.execute(text("""
            SELECT season_year, production_tonnes FROM crop_yield_observations
            WHERE commodity=:c AND country=:o AND source=:src AND production_tonnes IS NOT NULL
            ORDER BY season_year
        """), {"c": args.commodity, "o": args.origin, "src": args.source}).fetchall()
    d = decompose({int(y): float(p) for y, p in rows if p})

    pts = []
    for y in sorted(set(res)):
        t = d["years"].get(y)
        if t and t.get("trend_full_window") and res[y] is not None:
            pts.append((res[y], t["climate_pct"]))
    print(f"{args.commodity}/{args.origin}  basins={'|'.join(basins)}  season={months}  n={len(pts)}")
    if len(pts) < 12:
        print("  too few overlapping years"); return 0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    r2, loo, b = ols1(xs, ys)
    sign = "higher fill -> higher yield" if b > 0 else "higher fill -> LOWER yield (wrong sign)"
    print(f"  reservoir fill  in-sample r2={r2:.3f}   LOO-CV r2={loo:.3f}   slope {b:+.2f}  ({sign})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
