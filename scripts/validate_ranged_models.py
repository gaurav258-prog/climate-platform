"""How the published crop models fare — in the TEST (in-sample fit) and against ACTUALS.

For each published/tested crop×origin this reports, honestly:
  n, driver              — the single best-validated driver (drought SPEI or soil_water)
  in-sample r2           — variance explained on the fit years (the optimistic number)
  LOO-CV r2 / RMSE       — leave-one-out cross-validation: refit WITHOUT each year, predict it.
                           This is the out-of-sample number — the honest "does it generalise",
                           and it always looks worse than in-sample. If in-sample >> LOO, it overfits.
  band coverage 68/95    — of the actual years, what fraction land inside the stated prediction
                           interval. A calibrated band catches ~68% / ~95%. This is what makes the
                           published RANGE trustworthy.
  worst years            — the model's call vs the real climate-attributable drop on the worst
                           observed years (the tail a risk product exists to get right).
"""
from __future__ import annotations

import argparse
import math

from sqlalchemy import text

from core.db.session import get_session
from ml.features.crop_cycle import decompose
from ml.features.drought import compute_indices, load_monthly, seasonal_by_year as spei_seasonal
from ml.features import soil_moisture as smf
from ml.scoring.drought_climatology import drought_score
from ml.scoring.soil_water_climatology import soil_water_score

NC = "data/era5_baseline/{r}_1991_2024_monthly.nc"
SM = "data/era5_baseline/{r}_1991_2024_soilmoisture.nc"


def _scores(region, driver, scale, months):
    if driver == "drought":
        return {r["year"]: drought_score(r["spei"])
                for r in spei_seasonal(compute_indices(load_monthly(NC.format(r=region)), scale=scale), months)
                if r.get("spei") is not None}
    smz = smf.anomaly(smf.load_root_zone(SM.format(r=region)))
    return {r["year"]: soil_water_score(r["sm_z"]) for r in smf.seasonal_by_year(smz, months)
            if r.get("sm_z") is not None}


def _ols(xs, ys):
    n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs); sxy = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    b = sxy/sxx; a = my - b*mx
    return a, b, mx, sxx


def report(commodity, origin, region, driver, season, source, scale=6):
    months = [int(m) for m in season.split(",")]
    sc = _scores(region, driver, scale, months)
    with get_session() as s:
        rows = s.execute(text("""SELECT season_year, production_tonnes FROM crop_yield_observations
            WHERE commodity=:c AND country=:o AND source=:src AND production_tonnes IS NOT NULL
            ORDER BY season_year"""), {"c": commodity, "o": origin, "src": source}).fetchall()
    d = decompose({int(y): float(p) for y, p in rows if p})
    pts = [(sc[y], d["years"][y]["climate_pct"], y) for y in sorted(sc)
           if d["years"].get(y) and d["years"][y].get("trend_full_window")]
    if len(pts) < 12:
        print(f"{commodity}/{origin}: only {len(pts)} usable years — skip"); return
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]; n = len(pts)
    my = sum(ys)/n; ss_t = sum((y-my)**2 for y in ys)

    a, b, mx, sxx = _ols(xs, ys)
    r2 = 1 - sum((ys[i]-(a+b*xs[i]))**2 for i in range(n))/ss_t
    rmse = math.sqrt(sum((ys[i]-(a+b*xs[i]))**2 for i in range(n))/(n-2))

    # leave-one-out CV
    loo_err = []
    for i in range(n):
        xt = xs[:i]+xs[i+1:]; yt = ys[:i]+ys[i+1:]
        ai, bi, _, _ = _ols(xt, yt)
        loo_err.append(ys[i] - (ai + bi*xs[i]))
    loo_rmse = math.sqrt(sum(e*e for e in loo_err)/n)
    loo_r2 = 1 - sum(e*e for e in loo_err)/ss_t

    # band coverage (prediction interval at the full-sample fit)
    def se(x): return rmse*math.sqrt(1 + 1/n + (x-mx)**2/sxx)
    in68 = sum(1 for i in range(n) if abs(ys[i]-(a+b*xs[i])) <= 1.0*se(xs[i]))
    in95 = sum(1 for i in range(n) if abs(ys[i]-(a+b*xs[i])) <= 2.0*se(xs[i]))

    print(f"\n{commodity}/{origin}  driver={driver}  n={n}  ({pts[0][2]}-{pts[-1][2]})")
    print(f"  in-sample r2 = {r2:.3f}   LOO-CV r2 = {loo_r2:.3f}   (in-sample RMSE {rmse:.1f}pp, LOO {loo_rmse:.1f}pp)")
    print(f"  band coverage: 68% band caught {in68}/{n} = {in68/n*100:.0f}%   95% band {in95}/{n} = {in95/n*100:.0f}%")
    print(f"  worst observed years (actual climate drop vs model call):")
    for x, y, yr in sorted(pts, key=lambda p: p[1])[:4]:
        pred = a + b*x
        print(f"    {yr}: score {x:4.1f}  actual {y:+6.1f}%  model {pred:+6.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.parse_args()
    report("Olive oil", "ES", "spain_olive", "drought", "4,5,6,7,8", "FAOSTAT QCL bulk")
    report("Durum wheat", "ES", "spain_olive", "soil_water", "3,4,5,6", "EUROSTAT apro_cpsh1")
    report("Wine grapes", "ES", "spain_olive", "drought", "4,5,6,7,8", "FAOSTAT QCL bulk")


if __name__ == "__main__":
    main()
