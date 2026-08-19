"""Compute & store the independent challenger verdict for every ranged crop calibration.

For each sc_commodity_fit (the champion OLS), rebuild the SAME per-year (hazard score, climate-loss)
panel it was fitted on, run an independent isotonic estimator on it, and store the agreement verdict in
sc_commodity_challenger. This is the model-risk corroboration behind a published ranged euro — a second
method, computed from the golden data, never typed.

    python -m scripts.compute_challengers            # compute + store all
    python -m scripts.compute_challengers --dry-run  # print, don't persist
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from core.db.session import get_session
from ml.features.challenger import CHALLENGER_VERSION, isotonic_challenger
from ml.features.crop_cycle import decompose
from scripts.fit_ranged_crop import _drought_scores, _heat_scores, _soil_water_scores


def _panel(session, commodity: str, origin: str, driver: str, region: str,
           months: list, spei_scale: int) -> list:
    """Rebuild the champion's (hazard_score, climate_loss_pct) pairs from the golden panel."""
    if driver == "drought":
        scores = _drought_scores(region, spei_scale or 6, months)
    elif driver == "heat":
        scores = _heat_scores(region, months)
    elif driver == "soil_water":
        scores = _soil_water_scores(region, months)
    else:
        return []
    rows = session.execute(text("""
        SELECT season_year, production_tonnes FROM crop_yield_observations
        WHERE commodity = :c AND country = :o AND source LIKE 'FAOSTAT%' AND production_tonnes IS NOT NULL
        ORDER BY season_year
    """), {"c": commodity, "o": origin}).fetchall()
    prod = {int(y): float(p) for y, p in rows}
    d = decompose(prod)
    pts = []
    for year, score in scores.items():
        t = d["years"].get(year)
        if t is not None and t.get("trend_full_window"):
            pts.append((float(score), float(t["climate_pct"])))
    return pts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with get_session() as s:
        fits = s.execute(text("""
            SELECT f.commodity_id, c.name, f.origin, f.hazard_driver, f.region_key, f.season_months,
                   f.spei_scale, f.slope, f.intercept, f.rmse, f.r2_oos
            FROM sc_commodity_fit f JOIN sc_commodities c ON c.commodity_id = f.commodity_id
            ORDER BY f.r2_oos DESC NULLS LAST
        """)).mappings().all()
        print(f"champions on file: {len(fits)}")
        n_written = 0
        for f in fits:
            pts = _panel(s, f["name"], f["origin"], f["hazard_driver"], f["region_key"],
                         list(f["season_months"]), f["spei_scale"])
            v = isotonic_challenger(pts, float(f["slope"]), float(f["intercept"]),
                                    float(f["rmse"] or 0.0))
            oos = f["r2_oos"]
            print(f"  {f['name']:12s}/{f['origin']} {f['hazard_driver']:10s} "
                  f"r2_oos={float(oos):.2f} -> {v['verdict']:11s} "
                  + (f"(MAD {v.get('mean_abs_divergence_pp')}pp vs tol {v.get('tolerance_pp')}pp; "
                     f"champion {v.get('champion_at_ref_pct')}% vs challenger {v.get('challenger_at_ref_pct')}% @score {v.get('ref_score')})"
                     if v["verdict"] != "insufficient" else f"(n={v['n_years']})"))
            if args.dry_run:
                continue
            s.execute(text("""
                INSERT INTO sc_commodity_challenger
                    (commodity_id, origin, hazard_driver, method, n_years, mean_abs_divergence_pp,
                     tolerance_pp, ref_score, champion_at_ref_pct, challenger_at_ref_pct, verdict, challenger_version)
                VALUES (:cid, :o, :d, :m, :n, :mad, :tol, :ref, :cr, :hr, :verdict, :ver)
                ON CONFLICT (commodity_id, origin, hazard_driver) DO UPDATE SET
                    method=EXCLUDED.method, n_years=EXCLUDED.n_years,
                    mean_abs_divergence_pp=EXCLUDED.mean_abs_divergence_pp, tolerance_pp=EXCLUDED.tolerance_pp,
                    ref_score=EXCLUDED.ref_score, champion_at_ref_pct=EXCLUDED.champion_at_ref_pct,
                    challenger_at_ref_pct=EXCLUDED.challenger_at_ref_pct, verdict=EXCLUDED.verdict,
                    challenger_version=EXCLUDED.challenger_version, computed_at=now()
            """), {"cid": f["commodity_id"], "o": f["origin"], "d": f["hazard_driver"],
                   "m": v["method"], "n": v["n_years"], "mad": v.get("mean_abs_divergence_pp"),
                   "tol": v.get("tolerance_pp"), "ref": v.get("ref_score"),
                   "cr": v.get("champion_at_ref_pct"), "hr": v.get("challenger_at_ref_pct"),
                   "verdict": v["verdict"], "ver": CHALLENGER_VERSION})
            n_written += 1
        print(f"{'(dry-run) ' if args.dry_run else ''}stored {n_written} challenger verdicts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
