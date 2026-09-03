"""Fit and persist a crop×origin's ranged calibration — the one place that WRITES `sc_commodity_fit`.

Extracted from `scripts/fit_ranged_crop.py` so the same fit+persist path is reused: the CLI (establish a new
calibration), the drift refresh (re-fit a stale one against current ERA5), and — later — the challenger (fit a
second, independent method on the identical panel). One writer means the published number can never come from
two divergent code paths.

The publish decision is the out-of-sample gate (`r2_oos ≥ RANGED_PUBLISH_FLOOR`); a below-floor fit is still
stored (tested, € withheld) so the product can honestly say a crop was validated and show its OOS number.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.features.crop_cycle import is_alternate_bearing
from ml.features.crop_fit import CropFit, fit_climate_on_score
from ml.features.crop_panel import scores_for
from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR

MIN_R2 = RANGED_PUBLISH_FLOOR          # the publish floor (single source of truth, audit T10)
FIT_VERSION = "ranged-fit-v0.1"


def _production(session: Session, commodity: str, origin: str, source: str) -> dict[int, float]:
    rows = session.execute(text("""
        SELECT season_year, production_tonnes FROM crop_yield_observations
        WHERE commodity = :c AND country = :o AND source = :src AND production_tonnes IS NOT NULL
        ORDER BY season_year
    """), {"c": commodity, "o": origin, "src": source}).fetchall()
    return {int(y): float(p) for y, p in rows}


def fit_calibration(session: Session, *, commodity: str, origin: str, region: str, driver: str,
                    spei_scale: int, months: list[int], source: str) -> Optional[CropFit]:
    """Rebuild the champion fit for one crop×origin from current ERA5 + observed production. No writes."""
    scores = scores_for(region, driver, months, spei_scale)
    if not scores:
        return None
    production = _production(session, commodity, origin, source)
    return fit_climate_on_score(production, scores, driver, allow_cycle=is_alternate_bearing(commodity))


def persist_fit(session: Session, fit: CropFit, *, commodity: str, origin: str, region: str, driver: str,
                spei_scale: int, months: list[int], commit: bool = True) -> dict:
    """Upsert the calibration + fit rows for a rebuilt CropFit. Returns a summary incl. the publish verdict."""
    publishes = fit.r2_oos is not None and fit.r2_oos >= MIN_R2
    cid = session.execute(text("SELECT commodity_id FROM sc_commodities WHERE name = :n"),
                          {"n": commodity}).scalar()
    if cid is None:
        raise ValueError(f"unknown commodity '{commodity}'")

    existing = session.execute(text(
        "SELECT 1 FROM sc_commodity_calibration WHERE commodity_id=:cid AND origin=:o"
    ), {"cid": cid, "o": origin}).first()
    if existing is None:
        session.execute(text("""
            INSERT INTO sc_commodity_calibration
                (commodity_id, origin, hazard_driver, region_key, season_months, impact_version)
            VALUES (:cid, :o, :d, :region, :season, :ver)
        """), {"cid": cid, "o": origin, "d": driver, "region": region, "season": months, "ver": FIT_VERSION})
    else:
        session.execute(text("""
            UPDATE sc_commodity_calibration
            SET hazard_driver = :d, region_key = COALESCE(region_key, :region),
                season_months = COALESCE(season_months, :season)
            WHERE commodity_id = :cid AND origin = :o
        """), {"d": driver, "region": region, "season": months, "cid": cid, "o": origin})

    note = ("OLS of cycle-decomposed climate anomaly on the " + driver + " score "
            + (f"(SPEI-{spei_scale}, " if driver == "drought"
               else "(grain-fill temperature-anomaly percentile, " if driver == "heat"
               else "(root-zone soil-moisture anomaly, ")
            + f"months {months}) over {fit.n_years} years; r2={fit.r2:.3f}. "
            + ("Published as a RANGE." if publishes else "BELOW the publish floor — stored, tested, € withheld."))
    session.execute(text("""
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
            fit_version=EXCLUDED.fit_version, source_note=EXCLUDED.source_note, created_at=now()
    """), {
        "cid": cid, "o": origin, "d": driver, "region": region, "season": months, "scale": spei_scale,
        "n": fit.n_years, "slope": round(fit.slope, 5), "intercept": round(fit.intercept, 5),
        "r2": round(fit.r2, 4), "rmse": round(fit.rmse, 5), "mean": round(fit.score_mean, 5),
        "sxx": round(fit.score_sxx, 5), "r2oos": fit.r2_oos, "cov": fit.band_cov68,
        "bfrom": fit.years[0], "bto": fit.years[-1], "ver": FIT_VERSION, "note": note,
    })
    if commit:
        session.commit()
    return {"commodity": commodity, "origin": origin, "driver": driver, "n_years": fit.n_years,
            "r2": round(fit.r2, 4), "r2_oos": fit.r2_oos, "publishes": publishes}
