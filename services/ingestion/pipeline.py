"""
Ingestion pipeline — orchestrates all active adapters.
Run: python -m services.ingestion.pipeline
Or triggered daily by a Kubernetes CronJob (infra/k8s/ingestion-cronjob.yaml).
"""
import logging
import sys

from services.ingestion.adapters.era5 import ERA5Adapter
from services.ingestion.adapters.glofas import GloFASAdapter
from services.ingestion.adapters.nasa_firms import NASAFIRMSAdapter
from services.ingestion.adapters.sentinel1_sar import Sentinel1SARAdapter
from services.ingestion.adapters.sentinel3_slstr import Sentinel3SLSTRAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

#
# Adapter registry — all 5 Sprint 2 adapters active.
# ERA5 and GloFAS skip silently when CDSAPI_KEY is not set.
# S1/S3 skip silently unless SENTINEL1_STUB/SENTINEL3_STUB=true or credentials are set.
#
ACTIVE_ADAPTERS = [
    NASAFIRMSAdapter(days=1),       # wildfire active fire (free, no auth)
    ERA5Adapter(),                   # temperature, precipitation, soil moisture, wind
    GloFASAdapter(),                 # river discharge (flood)
    Sentinel1SARAdapter(),           # SAR backscatter (flood) — stub or CDSE
    Sentinel3SLSTRAdapter(),         # land surface temperature (heat) — stub or CDSE
]


def run() -> None:
    logger.info(f"Starting ingestion pipeline — {len(ACTIVE_ADAPTERS)} adapters")
    total_written = 0
    failed = []

    for adapter in ACTIVE_ADAPTERS:
        name = adapter.__class__.__name__
        try:
            count = adapter.run()
            total_written += count
            logger.info(f"  {name}: {count} observations written")
        except Exception as exc:
            logger.error(f"  {name}: FAILED — {exc}", exc_info=True)
            failed.append(name)

    logger.info(
        f"Pipeline complete — {total_written} total observations written, "
        f"{len(failed)} adapter error(s)"
    )

    if failed:
        logger.error(f"Failed adapters: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    run()
