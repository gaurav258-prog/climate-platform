"""Which calibration a plot's yield shock is read from (calibration_protocol.json 'regional' → applies_to).

A crop's calibrations are keyed by origin: a country (ISO 3166-1, 'US') or a region (a region code of
services.reference.region_shapes, 'US-KS', 'ES42'). A plot inside a region whose calibration of the crop PUBLISHES
(ranged or backtested) reads that region's; every other plot reads its country's — a regional calibration never speaks
for the rest of its country, and a held one never withholds a country's published figure (a region's series is shorter
and noisier: a hold there is too little evidence at that scale, not evidence against the country's fit).
"""
from __future__ import annotations

from typing import Optional

TIER_ORDER = ("backtested", "ranged", "indicative", "uncalibrated")


def is_region(key: str | None) -> bool:
    """A region code of the region reference ('US-KS', 'ES42') rather than a country code ('US')."""
    from services.reference import regions
    return bool(key) and len(key) > 2 and regions.known(key)


PUBLISHING = ("backtested", "ranged")


def key_of(origin_cal: Optional[dict], plot: dict) -> Optional[str]:
    """The origin key a plot reads: its region when the crop's calibration there publishes, else its country."""
    region = plot.get("region")
    rc = (origin_cal or {}).get(region) if region else None
    return region if rc and rc.get("calibration_tier") in PUBLISHING else plot.get("origin")


def cal_of(origin_cal: Optional[dict], plot: dict) -> Optional[dict]:
    """The calibration a plot reads (None: neither its region nor its country has one)."""
    return (origin_cal or {}).get(key_of(origin_cal, plot))


def weakest_tier(tiers: list[str | None]) -> str:
    """The weakest tier among a country's plots' calibrations — an origin is only as validated as its least validated
    plot."""
    seen = [t if t in TIER_ORDER else "uncalibrated" for t in tiers] or ["uncalibrated"]
    return max(seen, key=TIER_ORDER.index)


def resolve_regions(commodities: list[dict], calibrations: dict) -> None:
    """Set plot['region'] (from its latitude and longitude) for the plots of every crop that holds a regional
    calibration — a plot with no coordinates, or outside every border, has no region and reads its country's."""
    need = {name for name, oc in (calibrations or {}).items() if any(is_region(k) for k in oc)}
    if not need:
        return
    from services.reference import region_shapes
    for c in commodities:
        if c["name"] not in need:
            continue
        for p in c["plots"]:
            lat, lon = p.get("lat"), p.get("lon")
            p["region"] = region_shapes.region_of(lat, lon) if lat is not None and lon is not None else None
