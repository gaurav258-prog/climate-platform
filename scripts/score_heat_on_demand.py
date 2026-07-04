"""
On-demand heat_acute scoring for an arbitrary point — the heat counterpart of
scripts/score_point_gridded_on_demand.py's run_flood_lookup/run_pollution_lookup/
run_wildfire_lookup (flagged there as follow-on work, not built in that pass).

Unlike flood/wildfire (a trained scorer.pkl) or pollution (a fixed AQI formula),
heat reuses ml/scoring/heat_climatology.py's heat_score(temp_c, clim_mean,
clim_std, ...) — the SAME climatology two-part model (absolute stress + anomaly)
scripts/score_cocoa_heat.py already runs in batch for the cocoa belt, just
pointed at climatology_baseline (any point on Earth, 1991-2020 monthly normals)
instead of the cocoa-only local .nc baseline.

Fetch: ml/features/heat_point.py's fetch_and_score() does ONE ERA5-Land request
(2m_temperature, today) for a small bbox around the query point, then looks up
climatology_baseline per fetched cell (nearest-neighbor, bounded-box, matching
calendar month) and scores each with heat_score(). See heat_point.py's
docstring for the K-vs-C unit-conversion decision.

Same nearest-neighbor-fill-the-exact-query-cell convention as flood/pollution/
wildfire: ERA5-Land's ~11km grid is coarser than an H3 res-8 cell, so the exact
query cell often isn't one the fetch naturally produced.
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.features.heat_point import fetch_and_score

logger = logging.getLogger(__name__)

MODEL_VERSION = "heat-climatology-v1-ondemand"
POINT_BBOX_DEG = 0.5  # small ad-hoc box around the query point, not a named region


def run_heat_lookup(lookup_id: str, lat: float, lon: float) -> None:
    """Background task: fetch+score heat_acute for one point, write
    canonical_scores, update the public_lookups row so the client's poll picks
    up the result.

    Reuses ml/scoring/heat_climatology.py's heat_score() exactly as scripts/
    score_cocoa_heat.py already runs it in batch — just against
    climatology_baseline (global, any point) instead of the cocoa-only local
    .nc baseline, and against "today's" ERA5-Land reading instead of a
    year-in-history's seasonal mean. NOTE: unlike this project's flood/wildfire
    on-demand scorers (which assume ERA5-Land's on-demand fetch never hits a
    "today rejected" publish-lag error), live testing here on 2026-07-04 DID hit
    exactly that (MultiAdaptorNoDataError, latest available = today - 5 days) —
    so this scorer applies the same margin services/ingestion/adapters/era5.py's
    ERA5Adapter already uses ("ERA5 lags ~5 days; default to 7 days ago"), via
    ml/features/heat_point.py's ERA5_LAND_LAG_DAYS default. Do not "fix" this by
    reverting to date.today()."""
    now = datetime.now(timezone.utc)
    try:
        area = [lat + POINT_BBOX_DEG, lon - POINT_BBOX_DEG, lat - POINT_BBOX_DEG, lon + POINT_BBOX_DEG]

        df = fetch_and_score(lat, lon, area=area, day=None,
                              scenario="baseline", horizon="current")
        if df.empty:
            raise RuntimeError(
                "no ERA5-Land cells with a matching climatology_baseline row for this "
                "bbox (likely over open ocean, or outside the climatology coverage)")

        records = [{
            "h3_cell": r.h3_cell, "risk_score": round(float(r.score), 2),
            "risk_bucket": score_to_bucket(float(r.score)).value,
            "shap_factors": json.dumps({
                "on_demand": True, "nearest_neighbor_fill": False,
                "temp_c": r.temp_c, "clim_mean_c": r.clim_mean_c, "clim_std_c": r.clim_std_c,
                "climatology_cell": r.climatology_cell, "baseline_period": "1991-2020",
            }),
        } for r in df.itertuples()]

        # ERA5-Land's ~11km grid spacing is much coarser than an H3 res-8 cell
        # (~0.7km²), so the query point's EXACT cell often isn't one of the cells
        # the fetch naturally produced. Nearest-neighbor-fill it from the closest
        # scored grid point, same convention as run_flood_lookup/run_pollution_
        # lookup/run_wildfire_lookup, flagged in shap_factors, not an
        # independently modeled point.
        query_cell = h3.latlng_to_cell(lat, lon, 8)
        if not any(r["h3_cell"] == query_cell for r in records):
            nearest = min(records, key=lambda r: h3.great_circle_distance(
                (lat, lon), h3.cell_to_latlng(r["h3_cell"]), unit="km"))
            shap = json.loads(nearest["shap_factors"])
            shap["nearest_neighbor_fill"] = True
            records.append({
                "h3_cell": query_cell, "risk_score": nearest["risk_score"],
                "risk_bucket": nearest["risk_bucket"], "shap_factors": json.dumps(shap),
            })

        with get_session() as s:
            cells = [r["h3_cell"] for r in records]
            s.execute(text("""
                UPDATE canonical_scores SET valid_to=:now
                WHERE hazard_type='heat_acute' AND scenario='baseline' AND time_horizon='current'
                  AND valid_to IS NULL AND h3_cell = ANY(:cells)
            """), {"now": now, "cells": cells})
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, model_version, data_vintage, shap_factors,
                     scored_at, valid_from, valid_to)
                VALUES
                    (gen_random_uuid(), :h3_cell, 8, 'heat_acute', 'baseline', 'current',
                     :risk_score, :risk_bucket, :mv, :now, CAST(:shap_factors AS jsonb), :now, :now, NULL)
            """), [{**r, "mv": MODEL_VERSION, "now": now} for r in records])
            s.execute(text("""
                UPDATE public_lookups SET status='done', completed_at=:now WHERE lookup_id=:id
            """), {"now": now, "id": lookup_id})

    except Exception:
        logger.error("run_heat_lookup FAILED lookup_id=%s\n%s", lookup_id, traceback.format_exc())
        with get_session() as s:
            s.execute(text("""
                UPDATE public_lookups SET status='failed', completed_at=:now WHERE lookup_id=:id
            """), {"now": now, "id": lookup_id})
        raise
