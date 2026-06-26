"""
EMSC (European Mediterranean Seismological Centre) earthquake catalog adapter.

Ingests M≥4.5 events in the European region via the EMSC FDSN web service.
On each M≥5.0 event, a post-event damage assessment is automatically scheduled.

Data source: https://www.seismicportal.eu/fdsnws/event/1/
License: Free / open — EMSC real-time catalog
Coverage: lat 34–71, lon -30–45 (Europe + Med)
Cadence: Poll every 60 seconds for new events (used by monitor_seismic.py)
         or call once with a date range for historical backfill.

No API key required. Rate limit: 5 req/s (we poll at 0.017 req/s).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import h3
import requests

from core.db.models import SatelliteObservation
from core.types import HazardType
from .base import BaseAdapter, ADAPTER_VERSION

logger = logging.getLogger(__name__)

EMSC_FDSN_URL = "https://www.seismicportal.eu/fdsnws/event/1/query"

# European bounding box — [minlat, maxlat, minlon, maxlon]
EU_BBOX = (34.0, 71.0, -30.0, 45.0)

# Minimum magnitude to ingest as an observation
MIN_MAGNITUDE = 4.5

# Magnitude threshold above which we flag for immediate damage assessment
DAMAGE_ASSESSMENT_THRESHOLD = 5.0

# H3 resolution for event epicentre cell
H3_RESOLUTION = 8


class EMSCAdapter(BaseAdapter):
    """
    Fetches earthquake events from EMSC and writes them as SatelliteObservations
    with hazard_type='seismic'.

    Each observation represents one earthquake event.
    raw_value = magnitude (Mw / ML / mb depending on source)
    quality_flag = 0 (normal), 1 (preliminary — may be revised), 2 (automatic only)

    The cog_uri field is repurposed to store the EMSC event identifier so the
    damage assessment pipeline can look up event metadata without an extra join.
    """

    source_provider = "emsc_fdsn"

    def __init__(
        self,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        min_magnitude: float = MIN_MAGNITUDE,
    ):
        now = datetime.now(timezone.utc)
        self.end_dt = end_dt or now
        # Default: last 24 hours (for polling use-case)
        self.start_dt = start_dt or (now - timedelta(hours=24))
        self.min_magnitude = min_magnitude

    def fetch(self) -> list[dict]:
        params = {
            "format": "json",
            "minmagnitude": self.min_magnitude,
            "minlatitude": EU_BBOX[0],
            "maxlatitude": EU_BBOX[1],
            "minlongitude": EU_BBOX[2],
            "maxlongitude": EU_BBOX[3],
            "starttime": self.start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "endtime": self.end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "orderby": "time-asc",
            "limit": 1000,
        }
        logger.info(
            f"[EMSC] querying {self.start_dt.date()} → {self.end_dt.date()}, "
            f"M≥{self.min_magnitude}"
        )
        resp = requests.get(EMSC_FDSN_URL, params=params, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        features = data.get("features", [])
        logger.info(f"[EMSC] {len(features)} events returned")
        return features

    def to_observations(self, raw: list[dict]) -> list[SatelliteObservation]:
        observations = []
        for feature in raw:
            try:
                props = feature["properties"]
                coords = feature["geometry"]["coordinates"]  # [lon, lat, depth_km]

                lon, lat, depth_km = float(coords[0]), float(coords[1]), float(coords[2])
                magnitude = float(props["mag"])
                mag_type = props.get("magtype", "M")
                origin_time_str = props["time"]
                event_id = props.get("unid") or feature.get("id", "")
                flynn_region = props.get("flynn_region", "")
                source_catalog = props.get("source_catalog", "EMSC")

                # Parse origin time — EMSC returns ISO8601, may have variable fractional seconds
                # Handle formats like 1998-01-10T19:21:55.8+00:00 (0.8 sec) or 2025-12-24T23:18:59.47+00:00
                if origin_time_str.endswith("Z"):
                    origin_time_str = origin_time_str[:-1] + "+00:00"
                try:
                    origin_dt = datetime.fromisoformat(origin_time_str)
                except ValueError:
                    # If fromisoformat fails, try manual parsing with regex
                    import re
                    match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d+)([\+\-]\d{2}:\d{2})', origin_time_str)
                    if match:
                        dt_str, frac, tz = match.groups()
                        # Pad/truncate fractional seconds to 6 digits (microseconds)
                        frac = (frac + '000000')[:6]
                        normalized = f"{dt_str}.{frac}{tz}"
                        origin_dt = datetime.fromisoformat(normalized)
                    else:
                        raise ValueError(f"Cannot parse origin time: {origin_time_str}")

                # Map epicentre to H3 cell
                h3_cell = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)

                # Quality flag: 0=reviewed, 1=preliminary, 2=automatic
                status = props.get("evtype", "ke")
                quality_flag = 0 if status == "ke" else (1 if status == "se" else 2)

                obs = SatelliteObservation(
                    h3_cell=h3_cell,
                    h3_resolution=H3_RESOLUTION,
                    source_provider=f"{self.source_provider}_{source_catalog.lower()}",
                    hazard_type=HazardType.SEISMIC.value,
                    observed_at=origin_dt,
                    raw_value=magnitude,
                    raw_unit=f"Mw_{mag_type}",
                    quality_flag=quality_flag,
                    quality_notes=(
                        f"M{magnitude} {mag_type} at {depth_km:.1f}km depth | "
                        f"{flynn_region} | evid={event_id}"
                    ),
                    cog_uri=event_id,  # repurposed: stores EMSC event identifier
                    adapter_version=ADAPTER_VERSION,
                )
                observations.append(obs)

                if magnitude >= DAMAGE_ASSESSMENT_THRESHOLD:
                    logger.warning(
                        f"[EMSC] M{magnitude} event triggers damage assessment: "
                        f"lat={lat:.2f} lon={lon:.2f} depth={depth_km:.1f}km | {flynn_region}"
                    )
            except Exception as exc:
                logger.warning(f"[EMSC] skipping malformed event: {exc}")
                continue

        return observations

    @staticmethod
    def events_requiring_damage_assessment(
        lookback_hours: int = 24,
        min_magnitude: float = DAMAGE_ASSESSMENT_THRESHOLD,
    ) -> list[dict]:
        """
        Return recent M≥5.0 events as dicts with lat/lon/time/magnitude.
        Used by monitor_seismic.py to schedule SAR coherence acquisitions.
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=lookback_hours)
        params = {
            "format": "json",
            "minmagnitude": min_magnitude,
            "minlatitude": EU_BBOX[0],
            "maxlatitude": EU_BBOX[1],
            "minlongitude": EU_BBOX[2],
            "maxlongitude": EU_BBOX[3],
            "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "endtime": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "orderby": "time-asc",
        }
        resp = requests.get(EMSC_FDSN_URL, params=params, timeout=30)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        events = []
        for f in features:
            p = f["properties"]
            c = f["geometry"]["coordinates"]
            events.append({
                "event_id": p.get("unid") or f.get("id"),
                "magnitude": float(p["mag"]),
                "mag_type": p.get("magtype", "M"),
                "lat": float(c[1]),
                "lon": float(c[0]),
                "depth_km": float(c[2]),
                "origin_time": datetime.fromisoformat(p["time"].replace("Z", "+00:00")),
                "region": p.get("flynn_region", ""),
            })
        return events
