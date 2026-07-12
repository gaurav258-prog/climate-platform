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

import threading
import time

import httpx

from core.config import settings

USER_AGENT = "TellumenClimatePlatform/1.0 (https://tellumen.example; contact: support@tellumen.example)"

_last_request_time = 0.0
_rate_lock = threading.Lock()  # thread-safe so concurrent loaders share one rate budget


def _respect_rate_limit():
    """Honour the configured min interval between requests. Thread-safe, so
    parallel workers still respect a single geocoder's rate budget. When
    NOMINATIM_MIN_INTERVAL_S is 0 (a self-hosted instance) this is a no-op."""
    interval = settings.NOMINATIM_MIN_INTERVAL_S
    if interval <= 0:
        return
    global _last_request_time
    with _rate_lock:
        elapsed = time.monotonic() - _last_request_time
        if elapsed < interval:
            time.sleep(interval - elapsed)
        _last_request_time = time.monotonic()


def geocode(address: str) -> dict | None:
    """Address string -> {"lat": float, "lon": float, "display_name": str}, or None if not found."""
    _respect_rate_limit()
    r = httpx.get(
        settings.NOMINATIM_URL,
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
