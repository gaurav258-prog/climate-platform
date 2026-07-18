"""Head-to-head: does root-zone SOIL MOISTURE explain a crop better than SPEI?

The water-availability hypothesis, tested honestly and per crop. For a crop×origin, decompose the
yield series into its climate-attributable anomaly (cycle removed), then regress that on BOTH the
seasonal SPEI and the seasonal soil-moisture anomaly, over the same years, and compare r². Soil
moisture wins only if it explains MORE — never assumed. Also tries drought+SM together.

    python -m scripts.compare_water_drivers --commodity "Olive oil" --origin ES \
        --region spain_olive --season 4,5,6,7,8 --spei-scale 6 --source "FAOSTAT QCL bulk"
"""
from __future__ import annotations

import argparse
import math
import sys

from sqlalchemy import text

from core.db.session import get_session
from ml.features.crop_cycle import decompose
from ml.features.drought import compute_indices, load_monthly, seasonal_by_year as spei_seasonal
from ml.features import soil_moisture as sm


def _ols(X, y):
    n, k = len(y), len(X[0])
    XtX = [[sum(X[i][a] * X[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    Xty = [sum(X[i][a] * y[i] for i in range(n)) for a in range(k)]
    M = [XtX[i][:] + [Xty[i]] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c])); M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        for r in range(k):
            if r != c and M[r][c]:
                f = M[r][c] / pv
                for cc in range(c, k + 1):
                    M[r][cc] -= f * M[c][cc]
    beta = [M[i][k] / M[i][i] for i in range(k)]
    yh = [sum(beta[a] * X[i][a] for a in range(k)) for i in range(n)]
    my = sum(y) / n
    ss_t = sum((v - my) ** 2 for v in y)
    ss_r = sum((y[i] - yh[i]) ** 2 for i in range(n))
    r2 = 1 - ss_r / ss_t if ss_t else 0.0
    adj = 1 - (1 - r2) * (n - 1) / (n - k) if n > k else r2
    return r2, adj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commodity", required=True)
    ap.add_argument("--origin", required=True)
    ap.add_argument("--region", required=True)
    ap.add_argument("--season", default="4,5,6,7,8")
    ap.add_argument("--spei-scale", type=int, default=6)
    ap.add_argument("--source", default="FAOSTAT QCL bulk")
    args = ap.parse_args()
    months = [int(m) for m in args.season.split(",")]

    ds = load_monthly(f"data/era5_baseline/{args.region}_1991_2024_monthly.nc")
    spei = {r["year"]: r["spei"] for r in spei_seasonal(compute_indices(ds, scale=args.spei_scale), months)}
    smz = {r["year"]: r["sm_z"] for r in
           sm.seasonal_by_year(sm.anomaly(sm.load_root_zone(
               f"data/era5_baseline/{args.region}_1991_2024_soilmoisture.nc")), months)}

    with get_session() as s:
        rows = s.execute(text("""
            SELECT season_year, production_tonnes FROM crop_yield_observations
            WHERE commodity=:c AND country=:o AND source=:src AND production_tonnes IS NOT NULL
            ORDER BY season_year
        """), {"c": args.commodity, "o": args.origin, "src": args.source}).fetchall()
    d = decompose({int(y): float(p) for y, p in rows if p})

    pts = []
    for y in sorted(set(spei) & set(smz)):
        t = d["years"].get(y)
        if t and t.get("trend_full_window") and spei[y] is not None and smz[y] is not None:
            pts.append((spei[y], smz[y], t["climate_pct"]))
    ys = [p[2] for p in pts]
    print(f"{args.commodity}/{args.origin}  n={len(pts)} usable years")
    if len(pts) < 12:
        print("  too few overlapping years — inconclusive")
        return 0
    r2_spei, _ = _ols([[1, p[0]] for p in pts], ys)
    r2_sm, _ = _ols([[1, p[1]] for p in pts], ys)
    r2_both, adj_both = _ols([[1, p[0], p[1]] for p in pts], ys)
    print(f"  SPEI only          r2={r2_spei:.3f}")
    print(f"  soil-moisture only r2={r2_sm:.3f}")
    print(f"  both               r2={r2_both:.3f}  (adj {adj_both:.3f})")
    best = max(("SPEI", r2_spei), ("soil moisture", r2_sm), key=lambda t: t[1])
    print(f"  => better single driver: {best[0]} (r2={best[1]:.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
