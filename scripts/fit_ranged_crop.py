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

from sqlalchemy import text

from core.db.session import get_session
from ml.features.crop_fit import fit_climate_on_score
from ml.features.drought import compute_indices, load_monthly, seasonal_by_year
from ml.features import soil_moisture as smf
from ml.scoring.drought_climatology import drought_score
from ml.scoring.soil_water_climatology import soil_water_score

MIN_R2 = 0.40   # below this a driver explains too little to publish even as a range
NC_TEMPLATE = "data/era5_baseline/{region}_1991_2024_monthly.nc"
SM_TEMPLATE = "data/era5_baseline/{region}_1991_2024_soilmoisture.nc"
FIT_VERSION = "ranged-fit-v0.1"


def _drought_scores(region: str, scale: int, months: list[int]) -> dict[int, float]:
    ds = load_monthly(NC_TEMPLATE.format(region=region))
    seasonal = seasonal_by_year(compute_indices(ds, scale=scale), months)
    return {r["year"]: drought_score(r["spei"]) for r in seasonal if r.get("spei") is not None}


def _soil_water_scores(region: str, months: list[int]) -> dict[int, float]:
    """Per-year root-zone water-stress score from the soil-moisture anomaly — the better driver
    for dryland cereals (SPEI misses the deep antecedent soil water grain-fill draws on)."""
    smz = smf.anomaly(smf.load_root_zone(SM_TEMPLATE.format(region=region)))
    return {r["year"]: soil_water_score(r["sm_z"]) for r in smf.seasonal_by_year(smz, months)
            if r.get("sm_z") is not None}


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

    if args.driver == "drought":
        scores = _drought_scores(args.region, args.spei_scale, months)
    elif args.driver == "soil_water":
        scores = _soil_water_scores(args.region, months)
    else:
        print(f"driver '{args.driver}' not wired — use 'drought' or 'soil_water'")
        return 2

    with get_session() as s:
        rows = s.execute(text("""
            SELECT season_year, production_tonnes FROM crop_yield_observations
            WHERE commodity = :c AND country = :o AND source = :src
              AND production_tonnes IS NOT NULL
            ORDER BY season_year
        """), {"c": args.commodity, "o": args.origin, "src": args.source}).fetchall()
        production = {int(y): float(p) for y, p in rows}

        fit = fit_climate_on_score(production, scores, args.driver)
        if fit is None:
            print("too few usable, non-edge years overlap — no fit")
            return 1

        print(f"{args.commodity}/{args.origin} {args.driver} SPEI-{args.spei_scale} "
              f"{args.season}: n={fit.n_years} years {fit.years[0]}-{fit.years[-1]}")
        print(f"  slope={fit.slope:.4f}  intercept={fit.intercept:.2f}  "
              f"r2={fit.r2:.3f}  rmse={fit.rmse:.2f}pp")
        lo, mid, hi = fit.predict(85.0)   # a severe-drought score, illustrative
        print(f"  at drought score 85: climate {mid:.1f}%  (68% band {lo:.1f}%..{hi:.1f}%)")

        publishes = fit.r2 >= MIN_R2
        if publishes:
            print(f"  r2 {fit.r2:.3f} >= {MIN_R2} — publishes as a RANGE")
        else:
            print(f"  r2 {fit.r2:.3f} < {MIN_R2} — STORED but HELD (below the publish floor); the "
                  f"product will say it was tested and show this r², € withheld")
        if args.dry_run:
            print("  --dry-run: not persisted")
            return 0

        cid = s.execute(text("SELECT commodity_id FROM sc_commodities WHERE name = :n"),
                        {"n": args.commodity}).scalar()
        if cid is None:
            print(f"unknown commodity '{args.commodity}'")
            return 1

        # The fit ESTABLISHES the driver, so stamp it onto the calibration row — the tier view and
        # the engine both read the hazard from there. A crop we tested may have no calibration row
        # yet (only the world-share ones were seeded), so create one if missing; world_share is left
        # NULL (it drives the world-shock roll-up, which is withheld for a held crop anyway).
        # Whether it PUBLISHES is decided by r² in the view (>= floor), not here — a below-floor fit
        # is stored + visible but stays 'indicative'/held.
        existing = s.execute(text(
            "SELECT 1 FROM sc_commodity_calibration WHERE commodity_id=:cid AND origin=:o"
        ), {"cid": cid, "o": args.origin}).first()
        if existing is None:
            s.execute(text("""
                INSERT INTO sc_commodity_calibration
                    (commodity_id, origin, hazard_driver, region_key, season_months, impact_version)
                VALUES (:cid, :o, :d, :region, :season, :ver)
            """), {"cid": cid, "o": args.origin, "d": args.driver, "region": args.region,
                   "season": months, "ver": FIT_VERSION})
        else:
            s.execute(text("""
                UPDATE sc_commodity_calibration
                SET hazard_driver = :d, region_key = COALESCE(region_key, :region),
                    season_months = COALESCE(season_months, :season)
                WHERE commodity_id = :cid AND origin = :o
            """), {"d": args.driver, "region": args.region, "season": months, "cid": cid, "o": args.origin})

        s.execute(text("""
            INSERT INTO sc_commodity_fit
                (commodity_id, origin, hazard_driver, region_key, season_months, spei_scale,
                 n_years, slope, intercept, r2, rmse, score_mean, score_sxx,
                 r2_oos, band_cov68, baseline_from, baseline_to, fit_version, source_note)
            VALUES (:cid, :o, :d, :region, :season, :scale, :n, :slope, :intercept, :r2, :rmse,
                    :mean, :sxx, :r2oos, :cov, :bfrom, :bto, :ver, :note)
            ON CONFLICT (commodity_id, origin, hazard_driver) DO UPDATE SET
                region_key=EXCLUDED.region_key, season_months=EXCLUDED.season_months,
                spei_scale=EXCLUDED.spei_scale, n_years=EXCLUDED.n_years, slope=EXCLUDED.slope,
                intercept=EXCLUDED.intercept, r2=EXCLUDED.r2, rmse=EXCLUDED.rmse,
                score_mean=EXCLUDED.score_mean, score_sxx=EXCLUDED.score_sxx,
                r2_oos=EXCLUDED.r2_oos, band_cov68=EXCLUDED.band_cov68,
                baseline_from=EXCLUDED.baseline_from, baseline_to=EXCLUDED.baseline_to,
                fit_version=EXCLUDED.fit_version, source_note=EXCLUDED.source_note,
                created_at=now()
        """), {
            "cid": cid, "o": args.origin, "d": args.driver, "region": args.region,
            "season": months, "scale": args.spei_scale, "n": fit.n_years,
            "slope": round(fit.slope, 5), "intercept": round(fit.intercept, 5),
            "r2": round(fit.r2, 4), "rmse": round(fit.rmse, 5),
            "mean": round(fit.score_mean, 5), "sxx": round(fit.score_sxx, 5),
            "r2oos": fit.r2_oos, "cov": fit.band_cov68,
            "bfrom": fit.years[0], "bto": fit.years[-1], "ver": FIT_VERSION,
            "note": (f"OLS of cycle-decomposed climate anomaly on the {args.driver} score "
                     + (f"(SPEI-{args.spei_scale}, " if args.driver == "drought"
                        else "(root-zone soil-moisture anomaly, ")
                     + f"months {args.season}) over {fit.n_years} years; r2={fit.r2:.3f}. "
                     + ("Published as a RANGE." if publishes
                        else "BELOW the publish floor — stored, tested, € withheld.")),
        })
        print(f"  persisted (r2={fit.r2:.3f}, {'ranged/published' if publishes else 'held'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
