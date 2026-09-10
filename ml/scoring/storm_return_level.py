"""Storm return-level scale — the 1-in-N-year annual maximum tropical-cyclone wind at a point (v3).

The v1/v2 storm score was the strongest wind any past track ever produced at the point: a worst-event-on-record
scale. Its temporal holdout failed (ρ −0.27): where the worst storm already happened is not where the next one hits
hardest. What a supervisor's 1-in-N question asks is a FREQUENCY: how strong is the wind this place should expect
in a given return period. So v3 takes every season of the IBTrACS record (1981–), computes for each season the
maximum Modified-Rankine wind any track observation of that season produced at the point (0 when no storm came
within range), and reads the return level off those annual maxima — the 90th percentile for a 1-in-10 event. The
Saffir-Simpson wind → score anchors are unchanged, so a score of 65 still means hurricane-force (96 kt) — now as
the wind to expect once a decade, not the worst on record. Seasons can be capped (`max_season`) so the holdout
validator builds the level from ≤ 2018 and tests it against 2019+ observed peaks.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from ml.scoring.storm_physics import default_rmax_km, wind_speed_at_distance, wind_to_score

RECORD_FROM = 1981
RETURN_PERIOD_YEARS = 10
INFLUENCE_KM = 400.0
BBOX_DEG = 5.0


def _haversine(la1, lo1, la2, lo2):
    p1, p2 = np.radians(la1), np.radians(la2)
    dp, dl = np.radians(la2 - la1), np.radians(lo2 - lo1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def annual_max_wind(lat: float, lon: float, max_season: int | None = None) -> tuple[np.ndarray, int]:
    """Per-season maximum Rankine wind (kt) at the point over the record → (array over seasons, n_seasons)."""
    last = max_season or 9999
    with get_session() as s:
        rows = s.execute(text("""
            SELECT season_year, CAST(lat AS FLOAT), CAST(lon AS FLOAT), CAST(max_wind_kt AS FLOAT), CAST(rmw_km AS FLOAT), sshs_category
            FROM storm_events
            WHERE lat BETWEEN CAST(:a AS numeric) AND CAST(:b AS numeric) AND lon BETWEEN CAST(:c AS numeric) AND CAST(:d AS numeric)
              AND max_wind_kt IS NOT NULL AND season_year >= :y0 AND season_year <= :y1
        """), {"a": lat - BBOX_DEG, "b": lat + BBOX_DEG, "c": lon - BBOX_DEG, "d": lon + BBOX_DEG, "y0": RECORD_FROM, "y1": last}).all()
        y_max = s.execute(text("SELECT max(season_year) FROM storm_events WHERE season_year <= :y1"), {"y1": last}).scalar() or RECORD_FROM
    seasons = list(range(RECORD_FROM, int(y_max) + 1))
    out = np.zeros(len(seasons))
    if rows:
        arr = np.array([(r[0], r[1], r[2], r[3], r[4] if r[4] else default_rmax_km(r[5])) for r in rows], dtype=float)
        d = _haversine(lat, lon, arr[:, 1], arr[:, 2])
        near = d <= INFLUENCE_KM
        if near.any():
            a, d = arr[near], d[near]
            wind = np.array([float(wind_speed_at_distance(v, dist, rm)) for v, dist, rm in zip(a[:, 3], d, a[:, 4])])
            for season, w in zip(a[:, 0].astype(int), wind):
                i = season - RECORD_FROM
                if 0 <= i < len(out) and w > out[i]:
                    out[i] = w
    return out, len(seasons)


def return_level_kt(annual_max: np.ndarray, rp_years: int = RETURN_PERIOD_YEARS) -> float:
    """Empirical 1-in-N wind from annual maxima (zeros count: a quiet season is a real observation)."""
    if len(annual_max) < 10:
        return 0.0
    return float(np.quantile(annual_max, 1.0 - 1.0 / rp_years))


def storm_return_level_score(lat: float, lon: float, max_season: int | None = None) -> dict:
    am, n = annual_max_wind(lat, lon, max_season)
    rl = return_level_kt(am)
    return {"score": round(float(wind_to_score(rl)), 2), "return_level_kt": round(rl, 1), "n_seasons": n, "seasons_with_storm": int((am > 0).sum()),
            "worst_on_record_kt": round(float(am.max()) if len(am) else 0.0, 1)}
