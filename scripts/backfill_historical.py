"""
Historical backfill for Week 10 validation gate.

Fetches ERA5 reanalysis for two ground-truth events:
  - Rhine / Ahr valley flood:    2021-07-05 → 2021-07-15
  - Gironde / Bordeaux wildfire: 2022-07-10 → 2022-07-22

Each day fetches 7 variables (6 ERA5-Land + 1 runoff) = ~168 CDS requests.
Run time: ~60-90 minutes (CDS queue + download, each ~25-30s).
Progress is logged so you can leave it running.
"""
import logging
import sys
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from services.ingestion.adapters.era5 import ERA5Adapter
from services.ingestion.adapters.glofas import GloFASAdapter

EVENTS = [
    {
        "name": "Rhine / Ahr flood 2021",
        "start": date(2021, 7, 5),
        "end": date(2021, 7, 15),
        "note": "Extreme precipitation peaked July 14-15; precursors visible from July 5",
    },
    {
        "name": "Gironde / Bordeaux wildfire 2022",
        "start": date(2022, 7, 10),
        "end": date(2022, 7, 22),
        "note": "Second wave of fires; heat + drought + wind conditions from July 10",
    },
]


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def backfill_day(target_date: date) -> dict:
    counts = {"era5": 0, "runoff": 0}

    era5 = ERA5Adapter(target_date=target_date)
    counts["era5"] = era5.run()

    runoff = GloFASAdapter(target_date=target_date)
    counts["runoff"] = runoff.run()

    return counts


def main():
    grand_total = 0

    for event in EVENTS:
        days = list(daterange(event["start"], event["end"]))
        n = len(days)
        logger.info("")
        logger.info(f"{'=' * 60}")
        logger.info(f"  {event['name']}  ({n} days)")
        logger.info(f"  {event['note']}")
        logger.info(f"{'=' * 60}")

        event_total = 0
        for i, day in enumerate(days, 1):
            logger.info(f"  [{i:02d}/{n}] {day} ...")
            try:
                counts = backfill_day(day)
                day_total = sum(counts.values())
                event_total += day_total
                logger.info(
                    f"  [{i:02d}/{n}] {day} ✓  "
                    f"era5={counts['era5']}  runoff={counts['runoff']}  "
                    f"day_total={day_total}"
                )
            except Exception as exc:
                logger.error(f"  [{i:02d}/{n}] {day} FAILED: {exc}")

        logger.info(f"  Event total: {event_total:,} observations")
        grand_total += event_total

    logger.info("")
    logger.info(f"Backfill complete — {grand_total:,} total observations written")


if __name__ == "__main__":
    main()
