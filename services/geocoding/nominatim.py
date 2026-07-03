"""
Address -> coordinates, via Nominatim (OpenStreetMap's free public geocoder).

Nominatim's usage policy requires a max of 1 request/second and a real, identifying
User-Agent (not a generic library default) -- both honoured here. This is the right
tool for THIS platform's current scale (a demo/early-access lookup feature) but not a
production consumer-scale answer: Nominatim's public instance rate-limits hard, and
their policy discourages heavy commercial use without self-hosting. Flagged explicitly
as a known scaling limitation (docs/... methodology docs elsewhere in this project
follow the same "disclose the gap, don't hide it" convention) -- swap for a self-hosted
Nominatim instance or a paid provider (Google/Mapbox) if this needs real traffic.
"""
from __future__ import annotations

import time

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "TellumenClimatePlatform/1.0 (https://tellumen.example; contact: support@tellumen.example)"

_last_request_time = 0.0
_MIN_INTERVAL_S = 1.0  # Nominatim usage policy: max 1 request/second


def _respect_rate_limit():
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_INTERVAL_S:
        time.sleep(_MIN_INTERVAL_S - elapsed)
    _last_request_time = time.monotonic()


def geocode(address: str) -> dict | None:
    """Address string -> {"lat": float, "lon": float, "display_name": str}, or None if not found."""
    _respect_rate_limit()
    r = httpx.get(
        NOMINATIM_URL,
        params={"q": address, "format": "jsonv2", "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    r.raise_for_status()
    results = r.json()
    if not results:
        return None
    top = results[0]
    return {
        "lat": float(top["lat"]),
        "lon": float(top["lon"]),
        "display_name": top.get("display_name", address),
    }
