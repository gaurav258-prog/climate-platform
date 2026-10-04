"""Supply outlook (E164) — what the weather of the seasons the yield record does not hold yet says about production, per
origin, read only through PUBLISHED calibrations.

For a crop: every origin with a published calibration run. For each season whose months the weather build holds in full
but whose production the recipe's yield series does not yet report, the driver score is read through the published fit
as its 68% range of the climate anomaly (production against its trend):
  * a loss (mid below zero) is shown as a range only when the run passed the downside gate
  * a gain (mid above zero) is shown as a range only when the run passed the upside rules — capped at the wettest
    quartile's mean anomaly when rule 4 needed the cap
  * anything else is held, with the reason (no number)
A season in progress is reported with how many of its months are observed — never read through the fit (the fit is of
the full season). Own origins (the organisation's sourcing plots) come first; the others are its alternatives.

Context only: never an input to volume at risk, COGS-at-risk, KRIs or filings (tests/integration/test_supply_outlook.py).
"""
from __future__ import annotations

import math

from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.features import yield_series
from services.calibration import crop_area, runner


def _published(session: Session, commodity: str) -> list[dict]:
    return [dict(r) for r in session.execute(text("""
        SELECT r.run_id::text, r.spec_id::text, r.n_years, CAST(r.slope AS FLOAT) AS slope,
               CAST(r.intercept AS FLOAT) AS intercept, CAST(r.rmse AS FLOAT) AS rmse,
               CAST(r.score_mean AS FLOAT) AS score_mean, CAST(r.score_sxx AS FLOAT) AS score_sxx,
               CAST(r.r2_oos AS FLOAT) AS r2_oos, r.downside_pass, r.upside_pass, r.upside, r.decided_at
        FROM crop_calibration_runs r JOIN crop_calibration_specs s ON s.spec_id = r.spec_id
        WHERE r.status = 'published' AND s.retired_at IS NULL AND s.commodity = :c
        ORDER BY s.origin, s.driver"""), {"c": commodity}).mappings()]


def band(run: dict, score: float) -> tuple[float, float, float]:
    """The published fit's 68% prediction interval for a new year at this score (as ml.features.crop_fit.CropFit)."""
    mid = run["intercept"] + run["slope"] * score
    se = run["rmse"] * math.sqrt(1 + 1 / run["n_years"] + (score - run["score_mean"]) ** 2 / run["score_sxx"])
    return mid - se, mid, mid + se


def read_season(run: dict, score: float) -> dict:
    lo, mid, hi = band(run, score)
    up = run["upside"] or {}
    if mid < 0:
        if run["downside_pass"]:
            return {"reads": "loss", "range_pct": [round(lo, 1), round(mid, 1), round(hi, 1)]}
        return {"reads": "held", "why": "a loss is indicated, but the calibration does not pass the downside gate"}
    if run["upside_pass"]:
        if up.get("capped"):
            cap = (up.get("capped_line") or {}).get("wet_cap_pct")
            if cap is not None and mid > cap:
                lo, mid, hi = lo - (mid - cap), cap, hi - (mid - cap)
        return {"reads": "gain", "range_pct": [round(lo, 1), round(mid, 1), round(hi, 1)], "capped": bool(up.get("capped"))}
    why = ("a gain is indicated, but the upside is not judged — the calibration does not pass the downside gate"
           if not run["downside_pass"] else "a gain is indicated, but the upside rules did not pass ("
           + "; ".join(up.get("failed") or []) + ")")
    return {"reads": "held", "why": why}


def origin_outlook(session: Session, run: dict) -> dict:
    sp = runner.spec(session, run["spec_id"])
    observed = yield_series.series(session, sp["commodity"], sp["origin"], sp["yield_source"], sp["yield_region"])
    last_year = max(observed) if observed else None
    scores, inputs = (crop_area.scores(session, sp) if sp["driver"] != "soil_water" else ({}, {}))
    seasons = []
    for y in sorted(s for s in scores if last_year is None or s > last_year):
        seasons.append({"year": y, "score": scores[y], **read_season(run, scores[y])})
    in_progress = None
    last_month = inputs.get("last_month")
    if last_month:
        ly, lm = int(last_month[:4]), int(last_month[5:7])
        nxt = max([last_year or 0, *(s["year"] for s in seasons)]) + 1
        months = [(nxt - 1, m) for m in sp["season_prev_months"]] + [(nxt, m) for m in sp["season_months"]]
        seen = sum(1 for (y, m) in months if (y, m) <= (ly, lm))
        if 0 < seen < len(months):
            in_progress = {"year": nxt, "months_observed": seen, "months": len(months)}
    return {"origin": sp["origin"], "driver": sp["driver"], "recipe": sp["weather_kind"], "yield_source": sp["yield_source"],
            "last_reported_year": last_year, "r2_oos": run["r2_oos"], "downside_pass": run["downside_pass"],
            "upside_pass": run["upside_pass"], "seasons": seasons, "in_progress": in_progress,
            "weather_through": last_month}


def outlook(session: Session, commodity: str, own_origins: list[str]) -> dict:
    """The outlook of a crop: own origins first, then the alternatives; held origins say why."""
    rows = [origin_outlook(session, r) for r in _published(session, commodity)]
    own = set(own_origins)
    rows.sort(key=lambda r: (r["origin"] not in own, r["origin"], r["driver"]))
    for r in rows:
        r["own"] = r["origin"] in own
    covered = {r["origin"] for r in rows}
    return {"commodity": commodity, "origins": rows,
            "own_without_calibration": sorted(own - covered),
            "basis": "the published calibrations only — a range is shown where its gate passed; context, never part of "
                     "volume at risk, COGS-at-risk, KRIs or filings"}
