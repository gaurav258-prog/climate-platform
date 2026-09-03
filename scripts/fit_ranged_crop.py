"""Fit a crop×origin's multi-year hazard regression and persist it as a 'ranged' calibration.

This is the honest, non-circular alternative to a single-event backtest: regress the crop's
cycle-decomposed climate anomaly on its per-year hazard score across every usable year, and
store the line + r² + residual band. A crop that clears MIN_R2 but not a single clean event
becomes 'ranged' — its € publishes AS A RANGE.

Olive is the reference case: Spain, drought, SPEI-6 over Apr–Aug. The 6-month accumulation
window is agronomically pre-justified (olive is a deep-rooted perennial filled by the winter–
spring water balance, not a 3-month spring snapshot); it is NOT the window that merely maxed r².

    python -m scripts.fit_ranged_crop --commodity "Olive oil" --origin ES \
        --region spain_olive --driver drought --spei-scale 6 --season 4,5,6,7,8
"""
from __future__ import annotations

import argparse
import sys

from core.db.session import get_session
from services.intelligence.crop_calibration import MIN_R2, fit_calibration, persist_fit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commodity", required=True)
    ap.add_argument("--origin", required=True)
    ap.add_argument("--region", required=True)
    ap.add_argument("--driver", default="drought")
    ap.add_argument("--spei-scale", type=int, default=6)
    ap.add_argument("--season", default="4,5,6,7,8")
    ap.add_argument("--source", default="FAOSTAT QCL bulk")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    months = [int(m) for m in args.season.split(",")]

    with get_session() as s:
        fit = fit_calibration(s, commodity=args.commodity, origin=args.origin, region=args.region,
                              driver=args.driver, spei_scale=args.spei_scale, months=months, source=args.source)
        if fit is None:
            print(f"no fit — driver '{args.driver}' unwired, no ERA5 panel for '{args.region}', "
                  f"or too few usable overlapping years")
            return 1

        scale_lbl = f"SPEI-{args.spei_scale} " if args.driver == "drought" else ""
        print(f"{args.commodity}/{args.origin} {args.driver} {scale_lbl}"
              f"{args.season}: n={fit.n_years} years {fit.years[0]}-{fit.years[-1]}")
        print(f"  slope={fit.slope:.4f}  intercept={fit.intercept:.2f}  "
              f"r2={fit.r2:.3f}  rmse={fit.rmse:.2f}pp  r2_oos={fit.r2_oos:.3f}")
        lo, mid, hi = fit.predict(85.0)   # a severe hazard score, illustrative
        print(f"  at {args.driver} score 85: climate {mid:.1f}%  (68% band {lo:.1f}%..{hi:.1f}%)")

        publishes = fit.r2_oos is not None and fit.r2_oos >= MIN_R2   # gate on out-of-sample r² (audit F2)
        if publishes:
            print(f"  r2_oos {fit.r2_oos:.3f} >= {MIN_R2} — publishes as a RANGE (in-sample r2 {fit.r2:.3f})")
        else:
            _oos = f"{fit.r2_oos:.3f}" if fit.r2_oos is not None else "n/a"
            print(f"  r2_oos {_oos} < {MIN_R2} — STORED but HELD (below the publish floor); the "
                  f"product will say it was tested and show this out-of-sample r², € withheld")
        if args.dry_run:
            print("  --dry-run: not persisted")
            return 0

        persist_fit(s, fit, commodity=args.commodity, origin=args.origin, region=args.region,
                    driver=args.driver, spei_scale=args.spei_scale, months=months)
        print(f"  persisted (r2={fit.r2:.3f}, {'ranged/published' if publishes else 'held'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
