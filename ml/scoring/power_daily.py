"""Daily point series from NASA POWER (MERRA-2) — the one fetch behind the channels that need a 30-year daily
record at an arbitrary location (cold wave: T2M_MIN; chronic heat: T2M_MAX). Cached per (cell centre, parameter)
in-process; a failed or empty reply returns None and the caller says insufficient_data — never a fill.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
BASELINE = ("19910101", "20201231")


@lru_cache(maxsize=8192)
def daily_by_year(lat_r: float, lon_r: float, parameter: str) -> Optional[dict[str, list[float]]]:
    """{year: [daily values]} for years with ≥300 valid days, or None when fewer than 20 such years exist."""
    import requests
    try:
        r = requests.get(POWER_URL, params={"parameters": parameter, "community": "RE", "longitude": lon_r, "latitude": lat_r,
                                            "start": BASELINE[0], "end": BASELINE[1], "format": "JSON"}, timeout=60)
        if r.status_code != 200:
            return None
        series = r.json()["properties"]["parameter"][parameter]
    except Exception:
        return None
    by_year: dict[str, list[float]] = {}
    for day, v in series.items():
        if v is not None and v > -900:
            by_year.setdefault(day[:4], []).append(float(v))
    full = {y: vals for y, vals in by_year.items() if len(vals) >= 300}
    return full if len(full) >= 20 else None
