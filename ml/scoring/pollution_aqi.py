"""
Pollution hazard scoring — transparent, standard-anchored (not an ML black box),
same convention as every other hazard here (heat_climatology.py's thermal-stress
band, storm_physics.py's Rankine vortex, etc.).

Anchor: WHO Global Air Quality Guidelines, 2021 update (the current international
reference; supersedes the 2005 guidelines) — recommended AQG levels plus the
Interim Targets (IT-1..IT-4) WHO defines as stepwise progress milestones for
places not yet meeting the AQG. Values below are the OFFICIAL published numbers
(WHO, "Global Air Quality Guidelines" 2021, Table 0.1 / NBK574582), not estimates:

  Pollutant   Averaging   AQG    IT-4   IT-3   IT-2   IT-1
  PM2.5       24-hour     15     25     37.5   50     75      (µg/m³)
  PM10        24-hour     45     50     75     100    150     (µg/m³)
  NO2         24-hour     25     --     --     50     120     (µg/m³, no IT-3/IT-4 defined)
  SO2         24-hour     40     --     --     50     125     (µg/m³, no IT-3/IT-4 defined)
  O3          8-hour      100    --     --     120    160     (µg/m³, no IT-3/IT-4 defined)

24-hour (or 8-hour, for O3 — the standard sub-daily O3 metric; WHO's "peak
season" O3 guideline is a 6-month average, not usable for a single day's score)
values are used rather than annual means, since this scores CURRENT/forecast
conditions at a point in time, not a location's long-run chronic exposure.

Each pollutant maps to its own 0-100 sub-score by linear interpolation between
these named breakpoints (AQG→20, ..., IT-1→100 for the 5-point scale; AQG→33,
IT-2→67, IT-1→100 for the 3-point scale), capped at 100 beyond IT-1 — the same
"named real thresholds, not an arbitrary scale" choice as every other hazard's
methodology doc. The OVERALL score is the MAX across available pollutant
sub-scores (the standard multi-pollutant AQI convention: the worst pollutant
governs the reported index, e.g. US EPA AQI, EU CAQI) — never an average, which
would hide a single dangerously elevated pollutant behind cleaner ones.
"""
from __future__ import annotations

POLLUTION_MODEL_VERSION = "pollution-who-aqg-v0"

# (concentration µg/m³, score) breakpoints, ascending. First point is always (0, 0).
_BREAKPOINTS: dict[str, list[tuple[float, float]]] = {
    "pm25": [(0, 0), (15, 20), (25, 40), (37.5, 60), (50, 80), (75, 100)],
    "pm10": [(0, 0), (45, 20), (50, 40), (75, 60), (100, 80), (150, 100)],
    "no2":  [(0, 0), (25, 33), (50, 67), (120, 100)],
    "so2":  [(0, 0), (40, 33), (50, 67), (125, 100)],
    "o3":   [(0, 0), (100, 33), (120, 67), (160, 100)],
}


def _pollutant_score(pollutant: str, concentration: float | None) -> float | None:
    """Linear-interpolate a concentration onto its WHO-anchored 0-100 sub-score."""
    if concentration is None:
        return None
    points = _BREAKPOINTS[pollutant]
    if concentration <= 0:
        return 0.0
    for (c_lo, s_lo), (c_hi, s_hi) in zip(points, points[1:]):
        if concentration <= c_hi:
            frac = (concentration - c_lo) / (c_hi - c_lo)
            return round(s_lo + frac * (s_hi - s_lo), 1)
    return 100.0  # beyond IT-1 (the worst named WHO milestone) — capped, not extrapolated


def pollution_score(pm25: float | None = None, pm10: float | None = None,
                     no2: float | None = None, so2: float | None = None,
                     o3: float | None = None) -> dict:
    """0-100 pollution-hazard score from same-day pollutant concentrations (µg/m³).

    Returns {"score": float, "risk_bucket"-compatible via core.types.score_to_bucket,
    "driver": the pollutant that set the max, "sub_scores": {...}} so the worst
    pollutant is always visible, not averaged away.
    """
    raw = {"pm25": pm25, "pm10": pm10, "no2": no2, "so2": so2, "o3": o3}
    sub_scores = {p: _pollutant_score(p, c) for p, c in raw.items()}
    available = {p: s for p, s in sub_scores.items() if s is not None}
    if not available:
        return {"score": None, "driver": None, "sub_scores": sub_scores}
    driver = max(available, key=available.get)
    return {"score": available[driver], "driver": driver, "sub_scores": sub_scores}
