"""
On-demand scoring for GRIDDED (continuous-field) hazards at an arbitrary point —
the slow path of the "any address on Earth" lookup. Unlike seismic (a point-source
event catalog already fully ingested, scored synchronously in-request — see
scripts/score_point_on_demand.py), flood/wildfire/heat/drought/pollution need an
actual data fetch from Copernicus CDS/ADS, which this project's own experience shows
takes 2-14 minutes to queue. That's why this runs as a background job, not inline.

Flood was the first gridded hazard wired here, reusing the EXACT production model
already used for named historical events (scripts/score_event_to_canonical.py):
the same trained scorer.pkl, the same feature computation (ml/features/
flood_era5.py), just pointed at a small ad-hoc bbox around the query point (via
CDS's [N,W,S,E] area format) and "today" instead of a named event's date.

Pollution is the second, using ml/features/pollution_cams.py's
`fetch_cams_forecast` (the live/near-real-time CAMS product) -- deliberately NOT
`fetch_cams_reanalysis`, which scripts/backtest_pollution.py uses instead: the
reanalysis product assimilates real observations after the fact so it's the
right tool for reconstructing a PAST event, but has the same multi-day lag as
ERA5-Land, so it can never answer "what's the air like right now." The forecast
archive is genuinely the correct choice for a live lookup, even though backtest_
pollution.py separately found it under-samples acute, hyper-local smoke plumes
when misapplied to a past event -- two different products for two different
questions, not one flawed product used everywhere.

Wildfire is the third, reusing models/wildfire_firms/scorer.pkl (trained on real
FIRMS burn labels, 5 features: wind speed, relative humidity, days-since-rain,
leaf-area-index fuel load, soil moisture — see ml/features/wildfire_era5.py) --
all 5 come from ONE ERA5-Land request, no separate satellite fetch needed.

Heat/drought would each need their own "compute_for_point" function following
this same shape -- not built yet, flagged as follow-on work, not silently
assumed to work.
"""
from __future__ import annotations

import json
import logging
import pickle
import traceback
from datetime import date, datetime, timedelta, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.features.flood_era5 import FEATURE_COLS, fetch_era5, compute_features
from ml.features.pollution_cams import fetch_cams_forecast, compute_features as compute_pollution_features
from ml.features.wildfire_era5 import (FEATURE_COLS as WILDFIRE_FEATURE_COLS,
                                        fetch_era5 as fetch_era5_wildfire,
                                        compute_features as compute_wildfire_features)
from ml.scoring.pollution_aqi import pollution_score, POLLUTION_MODEL_VERSION

logger = logging.getLogger(__name__)

MODEL_PKL = "models/flood_multievent/scorer.pkl"
WILDFIRE_MODEL_PKL = "models/wildfire_firms/scorer.pkl"
POINT_BBOX_DEG = 0.5  # small ad-hoc box around the query point, not a named region


def _active_model_version(hazard: str) -> str:
    with get_session() as s:
        row = s.execute(text(
            "SELECT model_version FROM model_registry WHERE hazard_type=:h AND is_active LIMIT 1"
        ), {"h": hazard}).first()
    return row[0] if row else f"{hazard}-on-demand"


def run_flood_lookup(lookup_id: str, lat: float, lon: float) -> None:
    """Background task: fetch+score flood for one point, write canonical_scores,
    update the public_lookups row so the client's poll picks up the result."""
    now = datetime.now(timezone.utc)
    try:
        area = [lat + POINT_BBOX_DEG, lon - POINT_BBOX_DEG, lat - POINT_BBOX_DEG, lon + POINT_BBOX_DEG]
        scorer = pickle.load(open(MODEL_PKL, "rb"))
        version = _active_model_version("flood")

        ds = fetch_era5(area, date.today())
        df = compute_features(ds)
        ds.close()
        if df.empty:
            raise RuntimeError("no ERA5 cells returned for this bbox (likely over open ocean)")
        df["score"] = scorer.score_dataframe(df[FEATURE_COLS].copy())["score"].values

        records = [{
            "h3_cell": r.h3_cell, "risk_score": round(float(r.score), 2),
            "risk_bucket": score_to_bucket(float(r.score)).value,
            "shap_factors": json.dumps({"on_demand": True, "nearest_neighbor_fill": False}),
        } for r in df.itertuples()]

        # ERA5-Land's ~11km grid spacing is much coarser than an H3 res-8 cell
        # (~0.7km²), so the query point's EXACT cell often isn't one of the cells
        # the fetch naturally produced. Nearest-neighbor-fill it from the closest
        # scored grid point (same regional flood risk at this resolution) so a poll
        # on the exact query cell always resolves -- flagged in shap_factors as a
        # nearest-neighbor fill, not an independently modeled point, same "state the
        # simplification" convention used everywhere else in this project.
        query_cell = h3.latlng_to_cell(lat, lon, 8)
        if not any(r["h3_cell"] == query_cell for r in records):
            nearest = min(records, key=lambda r: h3.great_circle_distance(
                (lat, lon), h3.cell_to_latlng(r["h3_cell"]), unit="km"))
            records.append({
                "h3_cell": query_cell, "risk_score": nearest["risk_score"],
                "risk_bucket": nearest["risk_bucket"],
                "shap_factors": json.dumps({"on_demand": True, "nearest_neighbor_fill": True}),
            })

        with get_session() as s:
            cells = [r["h3_cell"] for r in records]
            s.execute(text("""
                UPDATE canonical_scores SET valid_to=:now
                WHERE hazard_type='flood' AND scenario='baseline' AND time_horizon='current'
                  AND valid_to IS NULL AND h3_cell = ANY(:cells)
            """), {"now": now, "cells": cells})
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, model_version, data_vintage, shap_factors,
                     scored_at, valid_from, valid_to)
                VALUES
                    (gen_random_uuid(), :h3_cell, 8, 'flood', 'baseline', 'current',
                     :risk_score, :risk_bucket, :mv, :now, CAST(:shap_factors AS jsonb), :now, :now, NULL)
            """), [{**r, "mv": version, "now": now} for r in records])
            s.execute(text("""
                UPDATE public_lookups SET status='done', completed_at=:now WHERE lookup_id=:id
            """), {"now": now, "id": lookup_id})

    except Exception:
        logger.error("run_flood_lookup FAILED lookup_id=%s\n%s", lookup_id, traceback.format_exc())
        with get_session() as s:
            s.execute(text("""
                UPDATE public_lookups SET status='failed', completed_at=:now WHERE lookup_id=:id
            """), {"now": now, "id": lookup_id})
        raise


def run_pollution_lookup(lookup_id: str, lat: float, lon: float) -> None:
    """Background task: fetch+score pollution for one point, write canonical_scores,
    update the public_lookups row so the client's poll picks up the result.

    Uses the live CAMS forecast (fetch_cams_forecast), NOT the reanalysis product
    scripts/backtest_pollution.py uses for historical events — see this module's
    docstring for why those are two different tools for two different questions.

    Requests `today - 1 day`, not `date.today()`: confirmed live that CAMS's
    00:00 forecast run for the CURRENT day is genuinely rejected ("not produced
    a valid combination of values") until that run has published — same class
    of publish-lag issue as ERA5Adapter's "ERA5 lags ~5 days; default to 7 days
    ago" convention, just a 1-day margin here instead of ERA5's 5-7."""
    now = datetime.now(timezone.utc)
    try:
        area = [lat + POINT_BBOX_DEG, lon - POINT_BBOX_DEG, lat - POINT_BBOX_DEG, lon + POINT_BBOX_DEG]

        ds = fetch_cams_forecast(area, date.today() - timedelta(days=1))
        df = compute_pollution_features(ds)
        ds.close()
        if df.empty:
            raise RuntimeError("no CAMS cells returned for this bbox (likely over open ocean)")

        records = []
        for r in df.itertuples():
            scored = pollution_score(pm25=r.pm25_ugm3, pm10=r.pm10_ugm3)
            records.append({
                "h3_cell": r.h3_cell, "risk_score": scored["score"],
                "risk_bucket": score_to_bucket(scored["score"]).value,
                "shap_factors": json.dumps({
                    "on_demand": True, "nearest_neighbor_fill": False, "driver": scored["driver"],
                    "pm25_ugm3": round(float(r.pm25_ugm3), 1), "pm10_ugm3": round(float(r.pm10_ugm3), 1),
                }),
            })

        # Same CAMS-grid-vs-H3-res8 resolution mismatch as flood — nearest-neighbor
        # fill the exact query cell if the fetch didn't naturally produce it.
        query_cell = h3.latlng_to_cell(lat, lon, 8)
        if not any(r["h3_cell"] == query_cell for r in records):
            nearest = min(records, key=lambda r: h3.great_circle_distance(
                (lat, lon), h3.cell_to_latlng(r["h3_cell"]), unit="km"))
            shap = json.loads(nearest["shap_factors"])
            shap["nearest_neighbor_fill"] = True
            records.append({"h3_cell": query_cell, "risk_score": nearest["risk_score"],
                             "risk_bucket": nearest["risk_bucket"], "shap_factors": json.dumps(shap)})

        with get_session() as s:
            cells = [r["h3_cell"] for r in records]
            s.execute(text("""
                UPDATE canonical_scores SET valid_to=:now
                WHERE hazard_type='pollution' AND scenario='baseline' AND time_horizon='current'
                  AND valid_to IS NULL AND h3_cell = ANY(:cells)
            """), {"now": now, "cells": cells})
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, model_version, data_vintage, shap_factors,
                     scored_at, valid_from, valid_to)
                VALUES
                    (gen_random_uuid(), :h3_cell, 8, 'pollution', 'baseline', 'current',
                     :risk_score, :risk_bucket, :mv, :now, CAST(:shap_factors AS jsonb), :now, :now, NULL)
            """), [{**r, "mv": POLLUTION_MODEL_VERSION, "now": now} for r in records])
            s.execute(text("""
                UPDATE public_lookups SET status='done', completed_at=:now WHERE lookup_id=:id
            """), {"now": now, "id": lookup_id})

    except Exception:
        logger.error("run_pollution_lookup FAILED lookup_id=%s\n%s", lookup_id, traceback.format_exc())
        with get_session() as s:
            s.execute(text("""
                UPDATE public_lookups SET status='failed', completed_at=:now WHERE lookup_id=:id
            """), {"now": now, "id": lookup_id})
        raise


def run_wildfire_lookup(lookup_id: str, lat: float, lon: float) -> None:
    """Background task: fetch+score wildfire for one point, write canonical_scores,
    update the public_lookups row so the client's poll picks up the result.

    Reuses models/wildfire_firms/scorer.pkl (trained on real FIRMS burn labels)
    exactly as scripts/build_multievent_wildfire.py trains/backtests it — same
    ERA5-Land fetch, same 5 features (ml/features/wildfire_era5.py), just pointed
    at a small ad-hoc bbox around the query point and "today" instead of a named
    fire's peak date. Empirically, ERA5-Land's on-demand fetch (unlike CAMS's
    forecast archive) has not hit a "today rejected" publish-lag error across
    every flood/wildfire test run in this project — no artificial margin added."""
    now = datetime.now(timezone.utc)
    try:
        area = [lat + POINT_BBOX_DEG, lon - POINT_BBOX_DEG, lat - POINT_BBOX_DEG, lon + POINT_BBOX_DEG]
        scorer = pickle.load(open(WILDFIRE_MODEL_PKL, "rb"))
        version = _active_model_version("wildfire")

        ds = fetch_era5_wildfire(area, date.today())
        df = compute_wildfire_features(ds)
        ds.close()
        if df.empty:
            raise RuntimeError("no ERA5-Land cells returned for this bbox (likely over open ocean)")
        df["score"] = scorer.score_dataframe(df[WILDFIRE_FEATURE_COLS].copy())["score"].values

        records = [{
            "h3_cell": r.h3_cell, "risk_score": round(float(r.score), 2),
            "risk_bucket": score_to_bucket(float(r.score)).value,
            "shap_factors": json.dumps({
                "on_demand": True, "nearest_neighbor_fill": False,
                "gfs_wind_speed_ms": round(float(r.gfs_wind_speed_ms), 1),
                "gfs_relative_humidity_pct": round(float(r.gfs_relative_humidity_pct), 1),
                "days_since_last_rain": round(float(r.days_since_last_rain), 1),
                "fuel_load_lai": round(float(r.fuel_load_lai), 2),
                "soil_moisture": round(float(r.soil_moisture), 3),
            }),
        } for r in df.itertuples()]

        # Same ERA5-Land-grid-vs-H3-res8 resolution mismatch as flood/pollution —
        # nearest-neighbor fill the exact query cell if the fetch didn't naturally
        # produce it.
        query_cell = h3.latlng_to_cell(lat, lon, 8)
        if not any(r["h3_cell"] == query_cell for r in records):
            nearest = min(records, key=lambda r: h3.great_circle_distance(
                (lat, lon), h3.cell_to_latlng(r["h3_cell"]), unit="km"))
            shap = json.loads(nearest["shap_factors"])
            shap["nearest_neighbor_fill"] = True
            records.append({"h3_cell": query_cell, "risk_score": nearest["risk_score"],
                             "risk_bucket": nearest["risk_bucket"], "shap_factors": json.dumps(shap)})

        with get_session() as s:
            cells = [r["h3_cell"] for r in records]
            s.execute(text("""
                UPDATE canonical_scores SET valid_to=:now
                WHERE hazard_type='wildfire' AND scenario='baseline' AND time_horizon='current'
                  AND valid_to IS NULL AND h3_cell = ANY(:cells)
            """), {"now": now, "cells": cells})
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, model_version, data_vintage, shap_factors,
                     scored_at, valid_from, valid_to)
                VALUES
                    (gen_random_uuid(), :h3_cell, 8, 'wildfire', 'baseline', 'current',
                     :risk_score, :risk_bucket, :mv, :now, CAST(:shap_factors AS jsonb), :now, :now, NULL)
            """), [{**r, "mv": version, "now": now} for r in records])
            s.execute(text("""
                UPDATE public_lookups SET status='done', completed_at=:now WHERE lookup_id=:id
            """), {"now": now, "id": lookup_id})

    except Exception:
        logger.error("run_wildfire_lookup FAILED lookup_id=%s\n%s", lookup_id, traceback.format_exc())
        with get_session() as s:
            s.execute(text("""
                UPDATE public_lookups SET status='failed', completed_at=:now WHERE lookup_id=:id
            """), {"now": now, "id": lookup_id})
        raise
