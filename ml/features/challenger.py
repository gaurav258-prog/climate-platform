"""Independent challenger for a ranged crop calibration — a second method that corroborates the champion.

The champion is an OLS line fitted on a crop×origin's per-year (hazard score, climate-attributable loss)
panel. The challenger is an ISOTONIC (monotone, shape-agnostic) regression on the SAME panel: it makes no
linearity assumption — only that more hazard is not-less loss — so if it tracks the champion, the linear
fit is corroborated by a genuinely different estimator; if it reveals a threshold/curvature the line
misses, that is a real model-risk flag.

Independence: the challenger is fitted ONLY from the (score, loss) pairs. The champion's slope/intercept
are used solely to compute the champion's prediction for the comparison — never to fit the challenger.
Agreement is judged against the champion's OWN residual scale (RMSE), not an arbitrary constant:
  agree   — mean|champion − challenger| ≤ RMSE (they differ by less than the champion's own noise)
  partial — ≤ 2·RMSE
  diverge — otherwise (materially different shape)
"""
from __future__ import annotations

CHALLENGER_VERSION = "challenger-isotonic-v1"
_MIN_YEARS = 12            # same floor as the champion fit — a handful of points challenges nothing
_TOL_FLOOR_PP = 3.0        # never call agreement tighter than 3 percentage points


def isotonic_challenger(pts: list, champion_slope: float, champion_intercept: float,
                        champion_rmse: float, ref_score: float = 85.0) -> dict:
    """pts: [(hazard_score, climate_loss_pct), ...] — the SAME panel the champion OLS used.
    Returns {method, n_years, verdict, mean_abs_divergence_pp, tolerance_pp, ref_score,
    champion_at_ref_pct, challenger_at_ref_pct, version}."""
    n = len(pts)
    if n < _MIN_YEARS:
        return {"method": "isotonic", "n_years": n, "verdict": "insufficient", "version": CHALLENGER_VERSION}

    import numpy as np
    from sklearn.isotonic import IsotonicRegression

    xs = np.array([float(p[0]) for p in pts])
    ys = np.array([float(p[1]) for p in pts])
    slope = float(champion_slope)
    # A hazard drives loss DOWN (climate_pct more negative as score rises) → isotonic decreasing.
    iso = IsotonicRegression(increasing=(slope >= 0), out_of_bounds="clip").fit(xs, ys)

    champ = champion_intercept + slope * xs
    chal = iso.predict(xs)
    mad = float(np.abs(champ - chal).mean())
    tol = max(float(champion_rmse or 0.0), _TOL_FLOOR_PP)
    verdict = "agree" if mad <= tol else ("partial" if mad <= 2 * tol else "diverge")

    # A single comparable number at a representative SEVERE score, clipped to the observed range
    # (the non-parametric challenger does not extrapolate beyond the data it saw).
    rs = min(float(ref_score), float(xs.max()))
    return {
        "method": "isotonic", "n_years": n, "verdict": verdict,
        "mean_abs_divergence_pp": round(mad, 2), "tolerance_pp": round(tol, 2),
        "ref_score": round(rs, 1),
        "champion_at_ref_pct": round(float(champion_intercept + slope * rs), 2),
        "challenger_at_ref_pct": round(float(iso.predict([rs])[0]), 2),
        "version": CHALLENGER_VERSION,
    }
