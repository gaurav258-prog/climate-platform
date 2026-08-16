"""Multi-year regression fit of a crop's climate-attributable shock on a hazard score.

This is what earns a crop the 'ranged' tier: NOT a single-event match (circular — the cocoa
trap), but a coefficient fitted across every usable year, carrying an honest r² and a residual
band. A crop where a driver explains only ~half the variance still has real, useful signal — it
just must be PUBLISHED AS A RANGE, never a false-precision point.

The fit is an ordinary least-squares line

    climate_pct(year)  ≈  intercept + slope · hazard_score(year)

over the years where the crop's cycle-decomposition is trustworthy (trend_full_window). We keep
enough of the fit to reconstruct a proper PREDICTION INTERVAL later — n, the score mean, and the
score sum-of-squares — so the band widens honestly for a hazard score far outside the training
range, instead of pretending the same ± everywhere.

Nothing here is crop-specific; the caller supplies the per-year score and the production series.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ml.features.crop_cycle import decompose


@dataclass
class CropFit:
    driver: str                 # hazard whose score was regressed (e.g. 'drought')
    n_years: int
    slope: float                # climate_pct per point of hazard score (expect < 0 for a hazard)
    intercept: float
    r2: float                   # in-sample r² (the optimistic number)
    rmse: float                 # residual std of climate_pct (percentage points)
    score_mean: float           # mean training hazard score  — for the prediction interval
    score_sxx: float            # Σ(score - mean)²             — for the prediction interval
    years: list                 # the years used, for provenance
    r2_oos: float = 0.0         # leave-one-out cross-validated r² — the HONEST predictive number
    band_cov68: float = 0.0     # fraction of years inside the 1σ prediction interval (~0.68 if honest)

    def predict(self, score: float, z: float = 1.0) -> tuple[float, float, float]:
        """Predicted climate anomaly at `hazard_score`, as (low, mid, high) in %.

        The band is a genuine prediction interval for a NEW year, so it widens for scores far
        from the training mean:  se = rmse · sqrt(1 + 1/n + (x-mean)²/Sxx).  `z` scales it
        (1 ≈ 68%, 2 ≈ 95%). mid is the regression line."""
        mid = self.intercept + self.slope * score
        se = self.rmse * math.sqrt(1.0 + 1.0 / self.n_years
                                   + ((score - self.score_mean) ** 2) / self.score_sxx)
        half = z * se
        return mid - half, mid, mid + half


def fit_climate_on_score(production: dict[int, float],
                         score_by_year: dict[int, float],
                         driver: str, allow_cycle: bool = True) -> Optional[CropFit]:
    """OLS of the climate anomaly on a per-year hazard score.

    production   : {year: production_tonnes} for the origin.
    score_by_year: {year: 0-100 hazard score} for the SAME driver, region and season.
    allow_cycle  : de-cycle the series (True) — correct ONLY for alternate-bearing perennials;
                   annual crops must pass False so a spurious cycle isn't removed (see crop_cycle).
    Returns None if too few usable, non-edge years overlap (a fit on a handful of points is
    exactly the over-fitting this whole effort exists to avoid)."""
    d = decompose(production, allow_cycle=allow_cycle)
    pts = []
    for year, score in score_by_year.items():
        t = d["years"].get(year)
        if t is not None and t.get("trend_full_window"):
            pts.append((score, t["climate_pct"], year))
    if len(pts) < 12:
        return None

    n = len(pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0 or syy == 0:
        return None

    slope = sxy / sxx
    intercept = my - slope * mx
    r = sxy / math.sqrt(sxx * syy)
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    # RMSE with the regression's 2 degrees of freedom removed — honest for a small sample.
    rmse = math.sqrt(sum(e * e for e in resid) / (n - 2)) if n > 2 else 0.0

    # Leave-one-out cross-validation: refit WITHOUT each year, predict it. This is the honest
    # out-of-sample number the Confidence Grade keys on — it always looks worse than in-sample,
    # and if it collapses the fit was overfit.
    ss_t = syy
    loo_sq = 0.0
    for i in range(n):
        xt = xs[:i] + xs[i + 1:]
        yt = ys[:i] + ys[i + 1:]
        m = n - 1
        mxi = sum(xt) / m
        myi = sum(yt) / m
        sxxi = sum((x - mxi) ** 2 for x in xt)
        if sxxi == 0:
            loo_sq += (ys[i] - myi) ** 2
            continue
        bi = sum((x - mxi) * (y - myi) for x, y in zip(xt, yt)) / sxxi
        ai = myi - bi * mxi
        loo_sq += (ys[i] - (ai + bi * xs[i])) ** 2
    r2_oos = 1.0 - loo_sq / ss_t if ss_t else 0.0

    # Band calibration: fraction of the training years that fall inside the 1σ prediction interval
    # — a well-calibrated 68% band catches ~68%. This is what makes the published RANGE honest.
    def _se(x):
        return rmse * math.sqrt(1.0 + 1.0 / n + ((x - mx) ** 2) / sxx)
    inside = sum(1 for i in range(n) if abs(resid[i]) <= _se(xs[i]))
    band_cov68 = inside / n

    return CropFit(
        driver=driver, n_years=n, slope=slope, intercept=intercept,
        r2=r * r, rmse=rmse, score_mean=mx, score_sxx=sxx,
        years=sorted(p[2] for p in pts),
        r2_oos=round(r2_oos, 4), band_cov68=round(band_cov68, 4),
    )
