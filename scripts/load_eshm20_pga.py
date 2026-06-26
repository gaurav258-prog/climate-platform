"""
Load ESHM20 static PGA hazard layer into satellite_observations.

One-time (or annual) script. Populates all EU H3 cells with Peak Ground Acceleration
at 475-year return period from the European Seismic Hazard Model 2020.

No API key needed — uses fallback zone-based approximation.
Output: ~6,000–8,000 satellite_observations rows with hazard_type='seismic'
"""
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from services.ingestion.adapters.seismic_hazard import SeismicHazardAdapter
from core.db.session import get_session

def main():
    logger.info("")
    logger.info("=" * 60)
    logger.info("  ESHM20 PGA Hazard Layer Loader")
    logger.info("=" * 60)
    logger.info("")

    # Instantiate adapter (uses fallback zone table if no GeoTIFF)
    adapter = SeismicHazardAdapter(geotiff_path=None)

    # Fetch PGA values
    logger.info("[ESHM20] fetching PGA values across EU...")
    raw_pga = adapter.fetch()
    logger.info(f"[ESHM20] {len(raw_pga)} grid points retrieved")

    # Convert to observations
    logger.info("[ESHM20] converting to SatelliteObservation format...")
    observations = adapter.to_observations(raw_pga)
    logger.info(f"[ESHM20] {len(observations)} observations prepared")

    if not observations:
        logger.error("[ESHM20] no observations generated — aborting")
        return 1

    # Write to DB
    logger.info("[ESHM20] writing to database...")
    try:
        with get_session() as session:
            session.add_all(observations)
        logger.info(f"[ESHM20] ✓ {len(observations)} observations committed")
    except Exception as exc:
        logger.error(f"[ESHM20] write failed: {exc}")
        return 1

    # Verify
    logger.info("[ESHM20] verifying...")
    with get_session() as session:
        from sqlalchemy import text
        count = session.execute(
            text("SELECT COUNT(*) FROM satellite_observations WHERE hazard_type='seismic' AND source_provider='eshm20_pga'")
        ).scalar()
        logger.info(f"[ESHM20] ✓ {count} seismic observations in DB")

    logger.info("")
    logger.info("=" * 60)
    logger.info("  ESHM20 load complete")
    logger.info("=" * 60)
    logger.info("")
    return 0

if __name__ == "__main__":
    sys.exit(main())
