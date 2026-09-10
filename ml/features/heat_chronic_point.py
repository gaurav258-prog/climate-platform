"""
On-demand chronic-heat scoring for an arbitrary point.

Unlike every other gridded hazard here (flood/wildfire/pollution/heat_acute/
drought), chronic heat needs NO live external fetch — it's purely a function
of the 30-year climatology_baseline table already built (see
core/db/migrations/versions/b3c4d5e6f7a8_climatology_baseline.py). That means
it scores SYNCHRONOUSLY, in-request, the same cost tier as seismic
(scripts/score_point_on_demand.py) — no CDS queue wait, no background job,
no Celery task needed for this one.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket

MODEL_VERSION = "heat-chronic-power-tmax-v2"
CLIMATOLOGY_BOX_DEG = 1.0  # same bounded-box nearest-neighbor convention as heat_point.py


def _monthly_climatology(lat: float, lon: float) -> dict[int, tuple[float, float]]:
    """All 12 months' (clim_mean_c, clim_std_c) for the nearest climatology_baseline
    grid point to (lat, lon) — one bounded-box query, not 12 separate ones."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT month, lat, lon, temp_mean_k, temp_std_k
            FROM climatology_baseline
            WHERE lat BETWEEN CAST(:lat_min AS numeric) AND CAST(:lat_max AS numeric)
              AND lon BETWEEN CAST(:lon_min AS numeric) AND CAST(:lon_max AS numeric)
        """), {
            "lat_min": lat - CLIMATOLOGY_BOX_DEG, "lat_max": lat + CLIMATOLOGY_BOX_DEG,
            "lon_min": lon - CLIMATOLOGY_BOX_DEG, "lon_max": lon + CLIMATOLOGY_BOX_DEG,
        }).mappings().all()
    if not rows:
        return {}

    # nearest grid point by (lat, lon) among the candidates -- pick its (lat, lon)
    # once, then only use rows AT that exact point (all 12 months share one location)
    nearest_latlon = min({(float(r["lat"]), float(r["lon"])) for r in rows},
                         key=lambda p: h3.great_circle_distance((lat, lon), p, unit="km"))
    return {
        int(r["month"]): (float(r["temp_mean_k"]) - 273.15, float(r["temp_std_k"]))
        for r in rows if (float(r["lat"]), float(r["lon"])) == nearest_latlon
    }


def score_heat_chronic_point(lat: float, lon: float, scenario: str = "baseline",
                             horizon: str = "current") -> dict:
    """Chronic heat at an arbitrary point — v2: the expected number of days per year with daily MAXIMUM
    temperature ≥ 30 °C, counted from 30 years of daily maxima at the location (NASA POWER / MERRA-2), shifted
    by the parametric warming delta for forward anchors. Replaces the v1 monthly-mean Gaussian proxy, which
    read near zero across Europe because a monthly mean of 30 °C is a desert, not a hot summer. Same anchors
    (score = 100 × days / 182.5). A cell scored by v1 is re-scored and the old row retired; the lane is
    append-only. No daily record → insufficient_data, never a fill."""
    from ml.scoring.heat_chronic import HOT_DAY_THRESHOLD_C, SATURATION_DAYS, _clip01
    from ml.scoring.power_daily import daily_by_year
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""SELECT CAST(risk_score AS FLOAT) rs, risk_bucket, model_version FROM canonical_scores
                               WHERE hazard_type='heat_chronic' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL"""),
                       {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex and ex["model_version"] == MODEL_VERSION:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}
    clat, clon = h3.cell_to_latlng(cell)
    by_year = daily_by_year(round(clat, 3), round(clon, 3), "T2M_MAX")
    if not by_year:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "NASA POWER daily maximum temperature is not available for this location."}
    from ml.scoring.frost_climatology import warming_delta
    warming = warming_delta(scenario, horizon, lat)
    days = sum(sum(1 for v in vals if v + warming >= HOT_DAY_THRESHOLD_C) for vals in by_year.values()) / len(by_year)
    risk = round(100.0 * _clip01(days / SATURATION_DAYS), 1)
    if ex:
        with get_session() as s:
            s.execute(text("""UPDATE canonical_scores SET valid_to = now() WHERE hazard_type='heat_chronic' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h
                              AND valid_to IS NULL AND model_version <> :mv"""), {"c": cell, "sc": scenario, "h": horizon, "mv": MODEL_VERSION})
    now = datetime.now(timezone.utc)
    shap = {"expected_hot_days_per_year": round(days, 1), "hot_day_threshold_c": HOT_DAY_THRESHOLD_C, "n_years": len(by_year), "warming_shift_c": round(warming, 2), "on_demand": True,
            "source": "NASA POWER (MERRA-2) daily T2M_MAX 1991–2020", "method": "observed count of days with daily maximum ≥ 30 °C over 30 years, parametric warming shift"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'heat_chronic', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane) WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk, "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
