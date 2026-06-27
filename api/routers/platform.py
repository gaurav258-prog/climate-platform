"""
Public read-only endpoints powering the consolidated platform UI.

No auth — these are aggregate, read-only views of the golden source and the model
registry, the same posture as /v1/scores/summary. They feed the four data-flow
tiers of the UI: Foundation, Models, Live & Events, Industries.
"""
from __future__ import annotations

import h3
from fastapi import APIRouter, Query
from sqlalchemy import text

from api.deps import DbSession
from core.types import score_to_bucket

router = APIRouter(prefix="/v1/platform", tags=["Platform"])


@router.get("/geo", summary="H3 risk cells for the live map")
def geo_scores(session: DbSession, hazard: str = Query(...),
               max_cells: int = Query(12000, ge=100, le=20000)):
    """Current canonical scores for a hazard as {h3_cell, score, bucket}. Sets larger
    than max_cells are progressively coarsened (res 7 → 4, mean) so the map stays light
    while keeping full res-8 detail wherever the data fits."""
    rows = session.execute(text("""
        SELECT h3_cell, CAST(risk_score AS FLOAT) AS risk
        FROM   canonical_scores
        WHERE  hazard_type = :h AND scenario='baseline'
        AND    time_horizon='current' AND valid_to IS NULL
    """), {"h": hazard}).mappings().all()
    base = [(r["h3_cell"], r["risk"]) for r in rows]
    resolution = 8
    if len(base) > max_cells:
        for res in (7, 6, 5, 4):
            agg: dict = {}
            for cell, risk in base:
                parent = h3.cell_to_parent(cell, res)
                a = agg.setdefault(parent, [0.0, 0])
                a[0] += risk; a[1] += 1
            if len(agg) <= max_cells or res == 4:
                base = [(k, v[0] / v[1]) for k, v in agg.items()]
                resolution = res
                break
    cells = [{"h3_cell": c, "score": round(s, 1), "bucket": score_to_bucket(s).value}
             for c, s in base]
    return {"hazard": hazard, "resolution": resolution, "count": len(cells), "cells": cells}


@router.get("/models", summary="Model registry — honest per-hazard metrics")
def models(session: DbSession):
    rows = session.execute(text("""
        SELECT hazard_type, model_version, algorithm, is_active,
               CAST(validation_auc AS FLOAT)             AS auc,
               CAST(validation_avg_precision AS FLOAT)   AS avg_precision,
               validation_note, training_cell_count,
               training_data_vintage::text              AS training_data_vintage,
               created_at
        FROM   model_registry
        ORDER  BY hazard_type, is_active DESC, created_at DESC
    """)).mappings().all()
    return {"models": [dict(r) for r in rows]}


@router.get("/verification", summary="Daily forecast-verification series")
def verification(session: DbSession, region: str = Query("Venezuela M7.5")):
    exists = session.execute(text("SELECT to_regclass('public.forecast_verification')")).scalar()
    if not exists:
        return {"region": region, "points": []}
    rows = session.execute(text("""
        SELECT as_of_date::text AS as_of_date,
               CAST(elapsed_days AS FLOAT)    AS elapsed_days,
               CAST(predicted_count AS FLOAT) AS predicted_count,
               CAST(sigma AS FLOAT)           AS sigma,
               observed_count,
               CAST(z_score AS FLOAT)         AS z_score,
               within_2sigma,
               CAST(largest_obs_mag AS FLOAT) AS largest_obs_mag,
               CAST(m5_forecast AS FLOAT)     AS m5_forecast,
               m5_occurred, note
        FROM   forecast_verification
        WHERE  region = :r
        ORDER  BY as_of_date
    """), {"r": region}).mappings().all()
    return {"region": region, "points": [dict(r) for r in rows]}


@router.get("/seismic-events", summary="Recent seismic events (live feed)")
def seismic_events(session: DbSession, days: int = Query(14, ge=1, le=90),
                   min_mag: float = Query(4.5, ge=0, le=10), limit: int = Query(200, le=1000)):
    rows = session.execute(text("""
        SELECT event_id, CAST(magnitude AS FLOAT) AS magnitude, mag_type,
               CAST(depth_km AS FLOAT)        AS depth_km,
               CAST(epicentre_lat AS FLOAT)   AS lat,
               CAST(epicentre_lon AS FLOAT)   AS lon,
               origin_time, region_name, source_catalog
        FROM   seismic_events
        WHERE  origin_time > now() - make_interval(days => :days)
        AND    magnitude >= :mm
        ORDER  BY origin_time DESC
        LIMIT  :lim
    """), {"days": days, "mm": min_mag, "lim": limit}).mappings().all()
    return {"count": len(rows), "events": [dict(r) for r in rows]}
