"""Site extreme still-water level for the coastal-flood channel — from tide gauges, not a constant.

The freeboard screen needs "how high does the sea actually get here" (tide + surge) before sea-level rise is added.
Until 2026-09-10 that was one generic 2.0 m allowance for every coast, which sat at the 80th percentile of observed
10-year maxima at US gauges and ranked observed extremes with rank correlation −0.32. This module replaces it with
the observed 1-in-10-year extreme still-water level at the nearest tide gauge:

  level(record) = 90th percentile of the annual maxima of (monthly max − record mean sea level), over years with
                  at least MIN_MONTHS_PER_YEAR observed months; a record needs MIN_YEARS such years.
  Only gauges within SEA_GAUGE_MAX_COAST_KM of the coastline qualify (GESLA also carries river and marsh gauges).
  level(site)   = level of the nearest qualifying gauge within GAUGE_RADIUS_KM (great-circle; one record per
                  gauge location, the longest). No gauge within range → None: the site's exposure cannot be
                  determined and no score is published for it (never the old constant in disguise).

Data: `tide_gauge_extremes` (GESLA-3 via the UHSLC ERDDAP, scripts/ingest_gesla_extremes.py). `max_year` lets the
validators rebuild the level from the years before a holdout window only.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

import numpy as np
from sqlalchemy import text

from core.db.session import get_session

GAUGE_RADIUS_KM = 250.0
MIN_YEARS = 10
MIN_MONTHS_PER_YEAR = 9
RETURN_PERIOD_YEARS = 10
SEA_GAUGE_MAX_COAST_KM = 10.0   # GESLA also holds river/marsh gauges; only gauges this close to the coastline measure the sea
_Q = 1.0 - 1.0 / RETURN_PERIOD_YEARS

_SQL = """
    WITH yr AS (
        SELECT record_id, min(station_name) AS station_name, min(country) AS country, min(lat) AS lat, min(lon) AS lon,
               year, max(max_m) AS mx, avg(mean_m) AS mn, count(*) AS n_months
        FROM tide_gauge_extremes WHERE year <= :y AND dist_to_coast_km <= :coast GROUP BY record_id, year
    ), rec AS (
        SELECT record_id, avg(mn) AS msl FROM yr WHERE n_months >= :mm GROUP BY record_id
    )
    SELECT yr.record_id, yr.station_name, yr.country, yr.lat, yr.lon, yr.year, yr.mx - rec.msl AS above_msl
    FROM yr JOIN rec USING (record_id) WHERE yr.n_months >= :mm ORDER BY yr.record_id, yr.year
"""


def gauge_levels(max_year: int = 9999, min_year: int = 0, session=None) -> list[dict]:
    """One row per gauge location: the 1-in-10-year extreme still-water level above the record's mean sea level.
    `min_year`..`max_year` bound the years used (validators hold out in time with these)."""
    def _run(s):
        return s.execute(text(_SQL), {"y": max_year, "mm": MIN_MONTHS_PER_YEAR, "coast": SEA_GAUGE_MAX_COAST_KM}).all()
    rows = _run(session) if session is not None else _run_own(_run)
    by_rec: dict[str, dict] = {}
    for rid, name, cc, lat, lon, year, above in rows:
        if year < min_year:
            continue
        r = by_rec.setdefault(rid, {"record_id": rid, "station_name": name, "country": cc, "lat": float(lat), "lon": float(lon), "annual": []})
        r["annual"].append(float(above))
    out = []
    for r in by_rec.values():
        if len(r["annual"]) < MIN_YEARS:
            continue
        am = np.asarray(r["annual"])
        out.append({**{k: v for k, v in r.items() if k != "annual"}, "n_years": int(len(am)),
                    "ewl_1in10_m": round(float(np.quantile(am, _Q)), 3), "max_on_record_m": round(float(am.max()), 3)})
    # one record per gauge location (providers overlap): keep the longest
    best: dict[tuple, dict] = {}
    for r in out:
        k = (round(r["lat"], 2), round(r["lon"], 2))
        if k not in best or r["n_years"] > best[k]["n_years"]:
            best[k] = r
    return sorted(best.values(), key=lambda r: r["record_id"])


def _run_own(fn):
    with get_session() as s:
        return fn(s)


@lru_cache(maxsize=4)
def _levels_cached(max_year: int) -> tuple:
    return tuple(gauge_levels(max_year))


def nearest_gauge(lat: float, lon: float, levels: list[dict] | tuple, radius_km: float = GAUGE_RADIUS_KM,
                  exclude_record: Optional[str] = None) -> Optional[dict]:
    """Nearest qualifying gauge within `radius_km`, with its distance; None when there is none."""
    from services.intelligence.model_validation import _hav_vec
    cand = [g for g in levels if g["record_id"] != exclude_record]
    if not cand:
        return None
    d = _hav_vec(lat, lon, np.array([g["lat"] for g in cand]), np.array([g["lon"] for g in cand]))
    i = int(d.argmin())
    if d[i] > radius_km:
        return None
    return {**cand[i], "dist_km": round(float(d[i]), 1)}


def extreme_water_level(lat: float, lon: float, max_year: int = 9999, levels=None) -> Optional[dict]:
    """{ewl_m, record_id, station_name, dist_km, n_years} for a site, or None when no gauge is within range."""
    g = nearest_gauge(lat, lon, levels if levels is not None else _levels_cached(max_year))
    if g is None:
        return None
    return {"ewl_m": g["ewl_1in10_m"], "record_id": g["record_id"], "station_name": g["station_name"],
            "dist_km": g["dist_km"], "n_years": g["n_years"], "max_on_record_m": g["max_on_record_m"]}
