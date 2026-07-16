"""
On-demand DROUGHT scoring for an arbitrary point -- the drought counterpart to
scripts/score_point_gridded_on_demand.py's run_flood_lookup / run_pollution_lookup
/ run_wildfire_lookup, flagged there as follow-on work. Kept in its own file
(not added to that shared module) per this task's integration instructions --
a separate wiring step imports run_drought_lookup from here into the lookup
router/BackgroundTasks call site.

DISCLOSED SCOPE SIMPLIFICATION: this scores an SPI-1 (single-month
precipitation-rate anomaly), NOT the batch/backtest path's SPI-3 (3-month
rolling accumulation, model_version "drought-spei-v0" in model_registry,
computed by ml/features/drought.py + scored by ml/scoring/drought_climatology.
py's Φ(-SPEI) mapping). See ml/features/drought_point.py's module docstring
for the full reasoning: climatology_baseline only stores a SINGLE calendar
month's mean/std, not a rolling-window statistic, so a correct SPI-3 baseline
cannot be reconstructed on-demand without re-deriving it from raw 30-year data.
model_version is therefore the distinct string "drought-spi1-on-demand-v0",
never presented as the SPEI model. The 0-100 conversion also deliberately uses
the real, citable McKee et al. (1993) named SPI severity thresholds (linear
interpolation between anchors), not drought_climatology.py's normal-CDF
Φ(-SPEI) -- a different, simpler, equally-disclosed v0 mapping for the
different on-demand statistic being scored.
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import date, datetime, timedelta, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.features.drought_point import (
    DROUGHT_MODEL_VERSION,
    CLIMATOLOGY_BOX_DEG,
    ERA5_LAND_LAG_DAYS,
    _nearest_climatology,
    compute_features,
    fetch_era5_precip,
    spi_to_drought_score,
)

logger = logging.getLogger(__name__)

POINT_BBOX_DEG = 0.5  # small ad-hoc box around the query point, same convention as flood/pollution/wildfire


def run_drought_lookup(lookup_id: str, lat: float, lon: float) -> None:
    """Background task: fetch+score drought for one point, write
    canonical_scores, update the public_lookups row so the client's poll
    picks up the result.

    v0 SPI-1 simplification (NOT the batch model's SPI-3) -- see this module's
    and ml/features/drought_point.py's docstrings for the full disclosure.
    Trailing ~30-day ERA5-Land precip rate vs. the current calendar month's
    climatology_baseline mean/std, McKee et al. (1993)-anchored 0-100 mapping.

    FIXED during wiring: this originally requested `date.today()` from CDS,
    which live testing (heat builder, 2026-07-04) proved gets rejected with
    MultiAdaptorNoDataError -- ERA5-Land's publish lag means "latest available"
    is today - 5 days, not today. Drought hits the identical
    reanalysis-era5-land dataset/adaptor via fetch_era5_precip, so it is
    equally subject to this and now applies the same ERA5_LAND_LAG_DAYS (7-day)
    margin as ml/features/heat_point.py and services/ingestion/adapters/era5.py.
    """
    now = datetime.now(timezone.utc)
    try:
        area = [lat + POINT_BBOX_DEG, lon - POINT_BBOX_DEG, lat - POINT_BBOX_DEG, lon + POINT_BBOX_DEG]
        end_day = date.today() - timedelta(days=ERA5_LAND_LAG_DAYS)

        ds = fetch_era5_precip(area, end_day)
        df = compute_features(ds)
        ds.close()
        if df.empty:
            raise RuntimeError("no ERA5-Land cells returned for this bbox (likely over open ocean)")

        month = end_day.month
        records = []
        for r in df.itertuples():
            cell_lat, cell_lon = h3.cell_to_latlng(r.h3_cell)
            clim = _nearest_climatology(cell_lat, cell_lon, month)
            if clim is None:
                continue  # can't score this cell without a climatology match
            std = clim["precip_std_mm"]
            if std <= 0:
                continue
            spi1 = (r.precip_recent_mm_day - clim["precip_mean_mm"]) / std
            score = spi_to_drought_score(spi1)
            records.append({
                "h3_cell": r.h3_cell, "risk_score": score,
                "risk_bucket": score_to_bucket(score).value,
                "shap_factors": json.dumps({
                    "on_demand": True, "nearest_neighbor_fill": False,
                    "spi1": round(spi1, 2),
                    "precip_recent_mm_day": round(float(r.precip_recent_mm_day), 3),
                    "climatology_mean_mm_day": round(clim["precip_mean_mm"], 3),
                    "climatology_std_mm_day": round(clim["precip_std_mm"], 3),
                    "climatology_baseline_period": "1991-2020",
                    "simplification": "SPI-1 (single-month precip anomaly), not SPI-3",
                }),
            })

        if not records:
            raise RuntimeError("no climatology_baseline match within the bbox neighborhood (no cells scored)")

        # ERA5-Land's ~11km grid spacing is much coarser than an H3 res-8 cell
        # (~0.7km²), so the query point's EXACT cell often isn't one of the
        # cells the fetch naturally produced -- same resolution mismatch as
        # flood/pollution/wildfire. Nearest-neighbor-fill it from the closest
        # scored grid point, flagged in shap_factors as a nearest-neighbor
        # fill, not an independently modeled point.
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
            # NOWCAST lane only — this is a point-in-time SPI1 reading for the public lookup.
            # It must never retire drought-spei-v0, the standing climatology that coffee's
            # 2021-drought calibration and backtest rest on (the same collision that wiped
            # cocoa's seasonal heat score). See migration score_lane_20260715.
            s.execute(text("""
                UPDATE canonical_scores SET valid_to=:now
                WHERE hazard_type='drought' AND scenario='baseline' AND time_horizon='current'
                  AND score_lane='nowcast'
                  AND valid_to IS NULL AND h3_cell = ANY(:cells)
            """), {"now": now, "cells": cells})
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, model_version, data_vintage, shap_factors,
                     scored_at, valid_from, valid_to, score_lane)
                VALUES
                    (gen_random_uuid(), :h3_cell, 8, 'drought', 'baseline', 'current',
                     :risk_score, :risk_bucket, :mv, :now, CAST(:shap_factors AS jsonb), :now, :now, NULL,
                     'nowcast')
            """), [{**r, "mv": DROUGHT_MODEL_VERSION, "now": now} for r in records])
            s.execute(text("""
                UPDATE public_lookups SET status='done', completed_at=:now WHERE lookup_id=:id
            """), {"now": now, "id": lookup_id})

    except Exception:
        logger.error("run_drought_lookup FAILED lookup_id=%s\n%s", lookup_id, traceback.format_exc())
        with get_session() as s:
            s.execute(text("""
                UPDATE public_lookups SET status='failed', completed_at=:now WHERE lookup_id=:id
            """), {"now": now, "id": lookup_id})
        raise
