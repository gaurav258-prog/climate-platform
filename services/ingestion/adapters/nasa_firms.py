import csv
import io
import logging
from datetime import datetime, timezone

import h3
import httpx

from core.config import settings
from core.db.models import SatelliteObservation
from core.types import HazardType
from .base import BaseAdapter, ADAPTER_VERSION

logger = logging.getLogger(__name__)

FIRMS_CSV_URL = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
    "/{api_key}/VIIRS_SNPP_NRT/{area}/{days}"
)

# EU bounding box for area query
EU_AREA = "W=-10,S=35,E=30,N=72"

# VIIRS confidence below this = flagged but not discarded
CONFIDENCE_THRESHOLD = 50


class NASAFIRMSAdapter(BaseAdapter):
    """
    NASA FIRMS VIIRS active fire detections for the EU bounding box.

    Source:  https://firms.modaps.eosdis.nasa.gov/
    Format:  CSV — one row per detection, ~10k rows/day for EU
    Cadence: every 3–6 hours
    Key field: FRP (Fire Radiative Power, MW) — intensity of active burning

    Requires FIRMS_API_KEY in .env (free, instant registration).
    """

    source_provider = "nasa_firms_viirs"

    def __init__(self, days: int = 1):
        self.days = days

    def fetch(self) -> list[dict]:
        if not settings.FIRMS_API_KEY:
            logger.warning("[FIRMS] FIRMS_API_KEY not set — skipping. Register free at firms.modaps.eosdis.nasa.gov")
            return []

        url = FIRMS_CSV_URL.format(
            api_key=settings.FIRMS_API_KEY,
            area=EU_AREA,
            days=self.days,
        )
        response = httpx.get(url, timeout=60)
        response.raise_for_status()

        reader = csv.DictReader(io.StringIO(response.text))
        return list(reader)

    def to_observations(self, raw: list[dict]) -> list[SatelliteObservation]:
        observations = []
        for row in raw:
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                frp = float(row.get("frp", 0) or 0)
                confidence = int(row.get("confidence", 0) or 0)

                acq_date = row.get("acq_date", "").strip()
                acq_time = row.get("acq_time", "0000").strip().zfill(4)
                observed_at = datetime.strptime(
                    f"{acq_date} {acq_time}", "%Y-%m-%d %H%M"
                ).replace(tzinfo=timezone.utc)

                quality_flag = 0 if confidence >= CONFIDENCE_THRESHOLD else 1
                quality_notes = (
                    None if quality_flag == 0
                    else f"VIIRS confidence {confidence}% below threshold {CONFIDENCE_THRESHOLD}%"
                )

                obs = SatelliteObservation(
                    h3_cell=h3.latlng_to_cell(lat, lon, settings.H3_RESOLUTION),
                    h3_resolution=settings.H3_RESOLUTION,
                    source_provider=self.source_provider,
                    hazard_type=HazardType.WILDFIRE.value,
                    observed_at=observed_at,
                    raw_value=frp,
                    raw_unit="MW",
                    quality_flag=quality_flag,
                    quality_notes=quality_notes,
                    adapter_version=ADAPTER_VERSION,
                )
                observations.append(obs)

            except (ValueError, KeyError) as exc:
                logger.warning(f"Skipping malformed FIRMS row: {exc} — {row}")

        return observations
