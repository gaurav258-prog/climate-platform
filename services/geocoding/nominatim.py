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


# Nominatim `addresstype` → our precision bucket + a base confidence for that bucket. A specific
# building/street resolves confidently; a bare city/region/country is a coarse hit we should flag.
_PRECISION = {
    "building": ("address", 0.92), "house": ("address", 0.92), "amenity": ("address", 0.88),
    "shop": ("address", 0.88), "office": ("address", 0.88), "leisure": ("address", 0.85),
    "road": ("street", 0.78), "residential": ("street", 0.76),
    "neighbourhood": ("city", 0.66), "suburb": ("city", 0.66), "hamlet": ("city", 0.64),
    "village": ("city", 0.64), "town": ("city", 0.62), "city": ("city", 0.6), "municipality": ("city", 0.58),
    "county": ("region", 0.45), "state_district": ("region", 0.42), "state": ("region", 0.4),
    "province": ("region", 0.4), "region": ("region", 0.4),
    "country": ("country", 0.28), "continent": ("country", 0.2),
}
_LOW_CONFIDENCE_BELOW = 0.55           # coarse/ambiguous hits the UI should ask the user to confirm


def _enrich(h: dict, fallback: str) -> dict:
    """Attach a precision bucket, a 0–1 confidence and a low_confidence flag to a raw Nominatim hit."""
    atype = (h.get("addresstype") or h.get("type") or "").lower()
    precision, base = _PRECISION.get(atype, ("place", 0.5))
    importance = float(h.get("importance") or 0.0)
    # nudge the bucket's base confidence by prominence, capped into the bucket's neighbourhood
    confidence = round(min(0.98, max(0.15, base + 0.10 * (importance - 0.5))), 2)
    return {
        "lat": float(h["lat"]), "lon": float(h["lon"]),
        "display_name": h.get("display_name", fallback),
        "precision": precision, "confidence": confidence,
        "low_confidence": confidence < _LOW_CONFIDENCE_BELOW or precision in ("region", "country"),
    }


def geocode_candidates(address: str, limit: int = 5) -> list[dict]:
    """Address string -> ranked list of candidates (best first, may be empty), each with
    {"lat","lon","display_name","precision","confidence","low_confidence"}.

    Powers the UI autocomplete so the user PICKS the right place instead of trusting the top hit —
    'Springfield' and truncated names ('Delhi' → Delhi/New Delhi/Delhi township) are exactly the
    ambiguous cases a single best-match gets wrong. The confidence/low_confidence flags let the UI
    warn on a coarse (city/region/country-level) hit rather than silently scoring a bad point.
    """
    _respect_rate_limit()
    r = httpx.get(
        settings.NOMINATIM_URL,
        params={"q": address, "format": "jsonv2", "limit": max(1, min(limit, 10)), "addressdetails": 0},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    r.raise_for_status()
    return [_enrich(h, address) for h in r.json()]


def geocode(address: str) -> dict | None:
    """Address string -> {"lat","lon","display_name"} best match, or None. (Single-hit convenience.)"""
    hits = geocode_candidates(address, limit=1)
    return hits[0] if hits else None
