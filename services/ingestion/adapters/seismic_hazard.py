"""
European Seismic Hazard Model (ESHM20) static adapter.

Loads pre-computed Peak Ground Acceleration (PGA) at 475-year return period
from the GFZ/EFEHR ESHM20 model and maps values to H3 cells at resolution 8.

This is a one-time (or annual) static load — seismic hazard does not change day-to-day.
It provides the background hazard layer for the seismic vulnerability score.

Data source: ESHM20 — https://doi.org/10.12686/eshm20
             GFZ Data Services, openly licensed (CC BY 4.0)

Fallback (no download): USGS Global Seismic Hazard Map (2020) at 1° resolution
             https://www.usgs.gov/programs/earthquake-hazards/seismic-hazard-maps-application

Usage:
    adapter = SeismicHazardAdapter()
    count = adapter.run()   # writes static PGA observations to satellite_observations

The hazard values are stored as SatelliteObservation with:
    hazard_type = 'seismic'
    source_provider = 'eshm20_pga'
    raw_value = PGA in g (peak ground acceleration)
    raw_unit = 'g_475yr'
    observed_at = model release date (2023-01-01 for ESHM20)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from core.db.models import SatelliteObservation
from core.types import HazardType
from .base import BaseAdapter, ADAPTER_VERSION

logger = logging.getLogger(__name__)

# ESHM20 release date — used as observed_at for static hazard observations
ESHM20_RELEASE = datetime(2023, 1, 1, tzinfo=timezone.utc)

# Approximate PGA (g) at 475-year return period by European seismic zone
# Source: ESHM20 published maps. Used as fallback when GeoTIFF is not downloaded.
# Zones are defined by (lat_min, lat_max, lon_min, lon_max, pga_g)
# Higher values = more hazardous. These are conservative approximations.
SEISMIC_ZONE_FALLBACK = [
    # High hazard — Apennines, Sicily, Calabria
    (37.0, 41.5, 13.0, 18.0, 0.28),
    # High hazard — Greece, Aegean, Corinth rift
    (36.0, 42.0, 19.0, 28.0, 0.35),
    # High hazard — Turkey border zone (Marmara)
    (40.0, 42.5, 26.0, 32.0, 0.30),
    # High hazard — Romania, Vrancea seismic zone
    (44.5, 47.0, 25.5, 28.0, 0.25),
    # Medium hazard — Balkans
    (41.0, 46.0, 14.0, 25.0, 0.15),
    # Medium hazard — Pyrenees, Iberian Peninsula
    (36.0, 44.0, -9.0, 3.0, 0.12),
    # Medium hazard — Alpine arc
    (44.0, 47.5, 6.0, 15.0, 0.10),
    # Low hazard — Central/Northern Europe
    (47.0, 71.0, -10.0, 30.0, 0.04),
    # Low hazard — British Isles
    (50.0, 60.0, -8.0, 2.0, 0.03),
]

H3_RESOLUTION = 8
# Approximate EU grid at 0.5° step for static hazard (coarser than daily observations)
LAT_STEP = 0.5
LON_STEP = 0.5


class SeismicHazardAdapter(BaseAdapter):
    """
    Loads static PGA hazard values into satellite_observations as background
    seismic hazard context for the scoring engine.

    If a GeoTIFF file is provided (downloaded from ESHM20), it will be used.
    Otherwise falls back to the zone-based approximation table above.

    The scoring engine combines PGA (background hazard) + building vulnerability
    + real-time EMSC event proximity to produce the H3 seismic risk score.
    """

    source_provider = "eshm20_pga"

    def __init__(self, geotiff_path: Optional[str] = None):
        self.geotiff_path = geotiff_path

    def fetch(self) -> list[dict]:
        if self.geotiff_path:
            return self._fetch_from_geotiff()
        return self._fetch_from_zone_table()

    def _fetch_from_zone_table(self) -> list[dict]:
        """Generate PGA grid points from the zone-based fallback table."""
        logger.info("[SeismicHazard] using zone-based PGA fallback (no GeoTIFF provided)")
        records = []
        lat = 34.0
        while lat <= 71.0:
            lon = -30.0
            while lon <= 45.0:
                pga = self._pga_for_point(lat, lon)
                records.append({"lat": lat, "lon": lon, "pga_g": pga})
                lon += LON_STEP
            lat += LAT_STEP
        logger.info(f"[SeismicHazard] generated {len(records)} zone grid points")
        return records

    def _pga_for_point(self, lat: float, lon: float) -> float:
        """Return PGA estimate from zone table (most specific zone wins)."""
        best_pga = 0.02  # background minimum for all of Europe
        best_area = float("inf")
        for z_lat_min, z_lat_max, z_lon_min, z_lon_max, pga in SEISMIC_ZONE_FALLBACK:
            if z_lat_min <= lat <= z_lat_max and z_lon_min <= lon <= z_lon_max:
                area = (z_lat_max - z_lat_min) * (z_lon_max - z_lon_min)
                if area < best_area:
                    best_area = area
                    best_pga = pga
        return best_pga

    def _fetch_from_geotiff(self) -> list[dict]:
        """Load PGA values from ESHM20 GeoTIFF (requires rasterio)."""
        try:
            import rasterio
            from rasterio.transform import rowcol
        except ImportError:
            logger.warning("[SeismicHazard] rasterio not installed, falling back to zone table")
            return self._fetch_from_zone_table()

        logger.info(f"[SeismicHazard] loading GeoTIFF from {self.geotiff_path}")
        records = []
        with rasterio.open(self.geotiff_path) as src:
            data = src.read(1)
            transform = src.transform
            nodata = src.nodata or -9999

            lat = 34.0
            while lat <= 71.0:
                lon = -30.0
                while lon <= 45.0:
                    try:
                        row, col = rowcol(transform, lon, lat)
                        if 0 <= row < data.shape[0] and 0 <= col < data.shape[1]:
                            val = float(data[row, col])
                            if val != nodata and val > 0:
                                records.append({"lat": lat, "lon": lon, "pga_g": val})
                    except Exception:
                        pass
                    lon += LON_STEP
                lat += LAT_STEP
        logger.info(f"[SeismicHazard] loaded {len(records)} GeoTIFF points")
        return records

    def to_observations(self, raw: list[dict]) -> list[SatelliteObservation]:
        import h3
        observations = []
        seen_cells = set()
        for rec in raw:
            try:
                cell = h3.latlng_to_cell(rec["lat"], rec["lon"], H3_RESOLUTION)
                if cell in seen_cells:
                    continue
                seen_cells.add(cell)

                pga = rec["pga_g"]
                # Normalise PGA to 0–1 quality notes for the scoring engine
                # (PGA > 0.30g = extreme; 0.15–0.30 = high; 0.05–0.15 = medium; <0.05 = low)
                if pga >= 0.30:
                    zone = "extreme"
                elif pga >= 0.15:
                    zone = "high"
                elif pga >= 0.05:
                    zone = "medium"
                else:
                    zone = "low"

                obs = SatelliteObservation(
                    h3_cell=cell,
                    h3_resolution=H3_RESOLUTION,
                    source_provider=self.source_provider,
                    hazard_type=HazardType.SEISMIC.value,
                    observed_at=ESHM20_RELEASE,
                    raw_value=pga,
                    raw_unit="g_475yr",
                    quality_flag=0,
                    quality_notes=f"PGA={pga:.3f}g @ 475yr RP | zone={zone} | ESHM20",
                    adapter_version=ADAPTER_VERSION,
                )
                observations.append(obs)
            except Exception as exc:
                logger.debug(f"[SeismicHazard] skipping point {rec}: {exc}")
        return observations
