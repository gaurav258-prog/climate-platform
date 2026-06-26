"""
Feature extraction pipeline.

Runs all three extractors for a given date.
Called after ingestion adapters have written to satellite_observations.

Usage:
    python -m ml.features.pipeline                  # yesterday
    python -m ml.features.pipeline --date 2021-07-13
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from .flood import FloodFeatureExtractor
from .heat import HeatFeatureExtractor
from .wildfire import WildfireFeatureExtractor

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EXTRACTORS = [
    FloodFeatureExtractor(),
    HeatFeatureExtractor(),
    WildfireFeatureExtractor(),
]


def run(target_date: date) -> dict[str, int]:
    results = {}
    for extractor in EXTRACTORS:
        name = type(extractor).__name__
        try:
            n = extractor.extract(target_date)
            results[name] = n
            logger.info(f"{name}: {n} cells")
        except Exception as exc:
            logger.error(f"{name} failed: {exc}", exc_info=True)
            results[name] = -1
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="ISO date, e.g. 2021-07-13 (default: yesterday)")
    args = parser.parse_args()

    if args.date:
        target = date.fromisoformat(args.date)
    else:
        target = date.today() - timedelta(days=1)

    logger.info(f"Extracting features for {target}")
    results = run(target)
    logger.info(f"Done: {results}")
