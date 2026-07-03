"""
Physics-based storm (tropical cyclone) hazard scoring.

A storm is neither a single point (earthquake epicentre, volcano vent) nor a smooth
continuous field (heat/drought) — it's a moving TRACK, a sequence of positions each
with its own wind field. This module scores ONE track observation's wind field at a
given distance; scripts/score_storm_event.py loops over every observation in a track
and takes the MAX per H3 cell — the same "max over multiple events" pattern already
used for seismic aftershock sequences (scripts/score_seismic_event.py).

Wind decay: Modified Rankine Vortex (a standard, named tropical-cyclone wind-field
model — not invented for this project, same "real physics, not an ML black box"
posture as seismic's Bakun & Wentworth IPE and volcanic's proximal/ashfall decay):
    V(r) = Vmax                      for r <= Rmax
    V(r) = Vmax * (Rmax / r) ** x    for r > Rmax
x = 0.5 here, a commonly-cited mid-range decay exponent in the cyclone literature
(values ~0.4-0.6 appear across studies) — a stated simplification, not fitted to
any specific storm.
"""
from __future__ import annotations

import numpy as np

DECAY_EXPONENT = 0.5

# Saffir-Simpson-referenced wind speed (knots) -> 0-100 hazard score anchor points.
# Piecewise-linear interpolation between named category thresholds, not a fitted curve.
_WIND_KT_ANCHORS = [0, 34, 64, 83, 96, 113, 137, 180]
_SCORE_ANCHORS = [0, 15, 35, 50, 65, 80, 95, 100]

# Category-scaled default Rmax (km) for track points where IBTrACS's real RMW is
# missing — order-of-magnitude only, same fallback posture as volcanic's
# vei_to_zone_radii (weaker storms have broader, less-defined wind cores).
_DEFAULT_RMAX_KM_BY_CAT = {5: 20.0, 4: 30.0, 3: 35.0, 2: 45.0, 1: 55.0, 0: 65.0, -1: 75.0}


def wind_speed_at_distance(vmax_kt, distance_km, rmax_km, x: float = DECAY_EXPONENT):
    """Modified Rankine Vortex: wind speed (kt) at a given distance from the storm centre."""
    d = np.maximum(np.asarray(distance_km, dtype=float), 0.01)
    rmax = max(float(rmax_km), 0.1)
    inside = d <= rmax
    decayed = float(vmax_kt) * (rmax / d) ** x
    return np.where(inside, float(vmax_kt), decayed)


def wind_to_score(wind_kt):
    """0-100 hazard score from wind speed (kt), Saffir-Simpson-referenced anchor points."""
    return np.clip(np.interp(np.asarray(wind_kt, dtype=float), _WIND_KT_ANCHORS, _SCORE_ANCHORS), 0.0, 100.0)


def default_rmax_km(sshs_category) -> float:
    """Category-scaled fallback when IBTrACS's real RMW is missing for a track point."""
    cat = int(sshs_category) if sshs_category is not None else 3
    return _DEFAULT_RMAX_KM_BY_CAT.get(cat, 35.0)


def track_point_score(distance_km, vmax_kt, rmax_km):
    """Wind speed -> 0-100 hazard score at a given distance from one track point."""
    wind = wind_speed_at_distance(vmax_kt, distance_km, rmax_km)
    return wind_to_score(wind)
