"""
Run the feature extraction pipeline over historical backfill dates.

Must be run AFTER scripts/backfill_historical.py completes so that
satellite_observations has ERA5 data for these dates.

Writes rows to ml_features_flood, ml_features_heat, ml_features_wildfire.
Each row = one H3 cell × one day of derived features.

Usage:
    python scripts/run_feature_pipeline_historical.py
    python scripts/run_feature_pipeline_historical.py --dry-run
"""
import argparse
import logging
import sys
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

EVENTS = [
    {
        "name": "Rhine / Ahr flood 2021",
        "start": date(2021, 7, 5),
        "end": date(2021, 7, 15),
    },
    {
        "name": "Gironde / Bordeaux wildfire 2022",
        "start": date(2022, 7, 10),
        "end": date(2022, 7, 22),
    },
]


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print dates without extracting")
    args = parser.parse_args()

    if args.dry_run:
        for event in EVENTS:
            days = list(daterange(event["start"], event["end"]))
            logger.info(f"{event['name']}: {len(days)} days  ({event['start']} → {event['end']})")
        return

    from ml.features.pipeline import run as extract

    grand_total = 0

    for event in EVENTS:
        days = list(daterange(event["start"], event["end"]))
        n = len(days)
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"  {event['name']}  ({n} days)")
        logger.info("=" * 60)

        event_total = 0
        for i, day in enumerate(days, 1):
            logger.info(f"  [{i:02d}/{n}] extracting features for {day} ...")
            try:
                results = extract(day)
                day_total = sum(v for v in results.values() if v >= 0)
                event_total += day_total
                logger.info(f"  [{i:02d}/{n}] {day} ✓  {results}  total={day_total}")
            except Exception as exc:
                logger.error(f"  [{i:02d}/{n}] {day} FAILED: {exc}", exc_info=True)

        logger.info(f"  Event subtotal: {event_total:,} feature rows written")
        grand_total += event_total

    logger.info("")
    logger.info(f"Feature extraction complete — {grand_total:,} total feature rows written")


if __name__ == "__main__":
    main()
