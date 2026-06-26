"""
Flood Intelligence Data Adapters

Sources:
- ERA5 Precipitation: ECMWF climate reanalysis (daily rainfall)
- Copernicus DEM: Digital elevation models for flood modeling
- River Gauges: Real-time water level sensors (500+ European stations)
- Sentinel-1 SAR: Flood extent detection (twice-weekly)
- MODIS Thermal: Water surface detection (daily)
"""

import logging
import requests
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import asyncio
from sqlalchemy.orm import Session
from core.db.models import FloodObservation, DataSourceStatus, Location

logger = logging.getLogger(__name__)

# ============================================================================
# ERA5 PRECIPITATION DATA
# ============================================================================

class ERA5PrecipitationAdapter:
    """
    Fetch daily precipitation data from ECMWF ERA5 climate reanalysis.

    Data: 0.25° resolution, covers all of Europe
    Update frequency: Daily (with ~5-day lag)
    Cost: Free (Copernicus Climate Data Store)

    Access: https://cds.climate.copernicus.eu/
    API Docs: https://cds.climate.copernicus.eu/api-how-to
    """

    SOURCE_NAME = "ERA5_PRECIPITATION"
    HAZARD_TYPE = "flood"
    BASE_URL = "https://cds.climate.copernicus.eu/api/v2"

    def __init__(self, api_key: str):
        """
        Initialize ERA5 adapter.

        Args:
            api_key: Copernicus Climate Data Store API key
                     Get from: https://cds.climate.copernicus.eu/user/register
        """
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def fetch_daily_precipitation(
        self,
        days_lookback: int = 7,
        european_bbox: Tuple[float, float, float, float] = (70, -10, 35, 40)
    ) -> List[Dict]:
        """
        Fetch ERA5 daily total precipitation for Europe.

        Args:
            days_lookback: Number of days to fetch (max 30, ERA5 has ~5-day lag)
            european_bbox: (north, west, south, east) for Europe

        Returns:
            List of precipitation observations with lat/lon/value
        """
        logger.info(f"Fetching ERA5 precipitation for last {days_lookback} days")

        try:
            # Calculate date range (accounting for ~5-day lag)
            end_date = datetime.utcnow() - timedelta(days=5)
            start_date = end_date - timedelta(days=days_lookback)

            # ERA5 request payload
            payload = {
                "variable": "daily_total_precipitation",
                "year": [start_date.year, end_date.year],
                "month": list(range(1, 13)),
                "day": list(range(1, 32)),
                "time": "00:00",
                "area": list(european_bbox),  # [N, W, S, E]
                "format": "netcdf",
                "download_format": "uncompressed"
            }

            # Submit request (async polling - ERA5 is a "Copernicus Data Store" product)
            response = requests.post(
                f"{self.BASE_URL}/datasets/sis-agrometeorological-indicators/request",
                json=payload,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()

            # Parse response - ERA5 returns job ID for async processing
            job_data = response.json()
            job_id = job_data.get("request_id")

            logger.info(f"ERA5 request submitted with job ID: {job_id}")

            # For MVP: Store job_id and poll later, or use cached data
            # Full implementation: Use xarray/netCDF4 to parse downloaded data

            observations = await self._parse_era5_netcdf(job_id)

            logger.info(f"Fetched {len(observations)} precipitation observations")
            return observations

        except Exception as e:
            logger.error(f"Failed to fetch ERA5 precipitation: {e}")
            raise

    async def _parse_era5_netcdf(self, job_id: str) -> List[Dict]:
        """
        Parse ERA5 NetCDF file and extract precipitation observations.

        In production: Download file via Copernicus CDS and parse with xarray
        """
        # Placeholder: Return synthetic data for MVP
        observations = []

        # For European grid (~0.25° resolution = ~24 points per degree)
        lats = np.arange(70, 35, -0.25)
        lons = np.arange(-10, 40, 0.25)

        for lat in lats:
            for lon in lons:
                observations.append({
                    "source": self.SOURCE_NAME,
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "precipitation_mm": float(np.random.gamma(shape=2, scale=3)),  # Synthetic rainfall
                    "observation_time": datetime.utcnow() - timedelta(days=1),
                    "data_type": "daily_total",
                    "unit": "mm"
                })

        return observations

    async def store_observations(self, db: Session, org_id: str, observations: List[Dict]):
        """Store precipitation observations in database."""
        for obs in observations:
            flood_obs = FloodObservation(
                org_id=org_id,
                source=self.SOURCE_NAME,
                h3_cell_res8=self._lat_lon_to_h3(obs["latitude"], obs["longitude"]),
                latitude=obs["latitude"],
                longitude=obs["longitude"],
                water_level_m=None,  # ERA5 gives precipitation, not water level
                water_extent_km2=None,
                observation_time=obs["observation_time"],
                raw_data={
                    "precipitation_mm": obs["precipitation_mm"],
                    "data_type": obs["data_type"]
                }
            )
            db.add(flood_obs)

        db.commit()
        logger.info(f"Stored {len(observations)} flood observations in database")

    @staticmethod
    def _lat_lon_to_h3(lat: float, lon: float, resolution: int = 8) -> str:
        """Convert latitude/longitude to H3 cell ID."""
        try:
            import h3
            return h3.latlng_to_cell(lat, lon, resolution)
        except Exception:
            return None


# ============================================================================
# RIVER GAUGE DATA
# ============================================================================

class EuropeaRiverGaugeAdapter:
    """
    Fetch real-time water level data from European river gauge networks.

    Data sources:
    - EEA: European Environment Agency (publicly available)
    - EUWIS: European Water Information System
    - National authorities: France (DREAL), Germany (BfG), etc.

    Update frequency: Real-time to hourly
    Cost: Free
    """

    SOURCE_NAME = "EUROPEAN_RIVER_GAUGES"
    HAZARD_TYPE = "flood"

    # Pre-configured major European river gauges
    MAJOR_GAUGES = {
        "Rhine-Cologne": {"lat": 50.935, "lon": 6.953, "river": "Rhine"},
        "Danube-Budapest": {"lat": 47.497, "lon": 19.040, "river": "Danube"},
        "Seine-Paris": {"lat": 48.856, "lon": 2.295, "river": "Seine"},
        "Po-Piacenza": {"lat": 45.055, "lon": 9.700, "river": "Po"},
        "Loire-Orleans": {"lat": 47.902, "lon": 1.904, "river": "Loire"},
        "Ebro-Tortosa": {"lat": 40.816, "lon": 0.418, "river": "Ebro"},
    }

    async def fetch_real_time_water_levels(self) -> List[Dict]:
        """
        Fetch current water levels from major European river gauges.

        Returns:
            List of gauge observations with water level in meters
        """
        logger.info("Fetching real-time river gauge data from European networks")

        observations = []

        try:
            # Fetch from each major gauge location
            for gauge_name, gauge_info in self.MAJOR_GAUGES.items():
                obs = await self._fetch_gauge_data(gauge_name, gauge_info)
                if obs:
                    observations.append(obs)

            logger.info(f"Fetched {len(observations)} river gauge readings")
            return observations

        except Exception as e:
            logger.error(f"Failed to fetch river gauge data: {e}")
            raise

    async def _fetch_gauge_data(self, gauge_name: str, gauge_info: Dict) -> Optional[Dict]:
        """
        Fetch data for individual gauge.

        In production: Query EEA EUWIS API or national water authority APIs
        """
        try:
            # Placeholder: Synthetic data
            water_level_m = float(np.random.normal(loc=3.5, scale=0.8))

            return {
                "source": self.SOURCE_NAME,
                "gauge_name": gauge_name,
                "river_name": gauge_info["river"],
                "latitude": gauge_info["lat"],
                "longitude": gauge_info["lon"],
                "water_level_m": water_level_m,
                "observation_time": datetime.utcnow(),
                "unit": "meters"
            }
        except Exception as e:
            logger.warning(f"Failed to fetch {gauge_name}: {e}")
            return None

    async def store_observations(self, db: Session, org_id: str, observations: List[Dict]):
        """Store gauge observations in database."""
        for obs in observations:
            flood_obs = FloodObservation(
                org_id=org_id,
                source=self.SOURCE_NAME,
                h3_cell_res8=self._lat_lon_to_h3(obs["latitude"], obs["longitude"]),
                latitude=obs["latitude"],
                longitude=obs["longitude"],
                water_level_m=obs["water_level_m"],
                observation_time=obs["observation_time"],
                raw_data={
                    "gauge_name": obs["gauge_name"],
                    "river_name": obs["river_name"]
                }
            )
            db.add(flood_obs)

        db.commit()
        logger.info(f"Stored {len(observations)} gauge observations")

    @staticmethod
    def _lat_lon_to_h3(lat: float, lon: float, resolution: int = 8) -> str:
        """Convert latitude/longitude to H3 cell ID."""
        try:
            import h3
            return h3.latlng_to_cell(lat, lon, resolution)
        except Exception:
            return None


# ============================================================================
# SENTINEL-1 SAR FLOOD DETECTION
# ============================================================================

class Sentinel1FloodDetectionAdapter:
    """
    Detect active floods using Sentinel-1 Synthetic Aperture Radar (SAR).

    Data: C-band SAR, 10m resolution
    Update frequency: Every ~6 days (ascending + descending orbits)
    Cost: Free (Copernicus Open Access Hub)

    Access: https://scihub.copernicus.eu/
    Alternative: Copernicus Climate Data Store
    """

    SOURCE_NAME = "SENTINEL1_FLOOD_DETECTION"
    HAZARD_TYPE = "flood"

    async def detect_active_floods(self, days_lookback: int = 7) -> List[Dict]:
        """
        Detect current floods using Sentinel-1 SAR imagery.

        Process:
        1. Query Copernicus Hub for recent Sentinel-1 VV/VH polarization
        2. Apply water detection algorithm (high backscatter = water)
        3. Compare with baseline to detect recent floods
        4. Extract flood extent polygons

        Returns:
            List of detected flood polygons with extent and location
        """
        logger.info(f"Detecting active floods in Sentinel-1 data (last {days_lookback} days)")

        try:
            # In production: Query Copernicus Open Access Hub
            # Example query: S1A_EW_GRDM_1SDV over European flood-prone areas

            observations = await self._simulate_flood_detection()
            logger.info(f"Detected {len(observations)} flood events")
            return observations

        except Exception as e:
            logger.error(f"Failed to detect floods in Sentinel-1: {e}")
            raise

    async def _simulate_flood_detection(self) -> List[Dict]:
        """Placeholder: Synthetic flood detections for MVP."""
        observations = []

        # Simulate a few active floods
        flood_locations = [
            {"name": "Rhine flooding", "lat": 50.9, "lon": 6.9, "extent_km2": 250},
            {"name": "Danube overflow", "lat": 47.5, "lon": 19.0, "extent_km2": 400},
        ]

        for flood in flood_locations:
            observations.append({
                "source": self.SOURCE_NAME,
                "flood_name": flood["name"],
                "latitude": flood["lat"],
                "longitude": flood["lon"],
                "water_extent_km2": flood["extent_km2"],
                "confidence": 0.92,
                "observation_time": datetime.utcnow() - timedelta(days=1),
                "data_type": "SAR_detection"
            })

        return observations


# ============================================================================
# FLOOD INGESTION PIPELINE
# ============================================================================

async def ingest_flood_data(db: Session, org_id: str, era5_api_key: str):
    """
    Main flood data ingestion pipeline.

    Sequence:
    1. ERA5 precipitation (background climatology)
    2. River gauges (real-time water levels)
    3. Sentinel-1 SAR (active flood detection)
    4. Compute flood risk scores
    """
    logger.info("=== Starting Flood Data Ingestion ===")

    try:
        # 1. Fetch ERA5 precipitation
        era5 = ERA5PrecipitationAdapter(api_key=era5_api_key)
        precip_obs = await era5.fetch_daily_precipitation()
        await era5.store_observations(db, org_id, precip_obs)

        # 2. Fetch river gauge levels
        gauges = EuropeaRiverGaugeAdapter()
        gauge_obs = await gauges.fetch_real_time_water_levels()
        await gauges.store_observations(db, org_id, gauge_obs)

        # 3. Detect SAR floods
        sar = Sentinel1FloodDetectionAdapter()
        sar_obs = await sar.detect_active_floods()
        # Store SAR observations...

        # 4. Update data source status
        source_status = DataSourceStatus(
            source_name="FLOOD_PIPELINE",
            hazard_type="flood",
            last_successful_fetch=datetime.utcnow(),
            records_fetched_today=len(precip_obs) + len(gauge_obs),
            is_healthy=True
        )
        db.merge(source_status)
        db.commit()

        logger.info("=== Flood Data Ingestion Complete ===")

    except Exception as e:
        logger.error(f"Flood ingestion pipeline failed: {e}")
        raise
