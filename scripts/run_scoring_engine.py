"""
Risk Scoring Engine — daily CLI entry point.

Runs the scoring engine for one or all hazard types on a given date.
This is the ONLY process that writes to canonical_scores.

Usage:
    # Score all hazards for yesterday
    python scripts/run_scoring_engine.py

    # Score a specific hazard and date
    python scripts/run_scoring_engine.py --hazard flood --date 2021-07-14

    # Dry run — compute but do not write
    python scripts/run_scoring_engine.py --dry-run

    # Score historical dates (after backfill + feature pipeline)
    python scripts/run_scoring_engine.py --hazard flood --date 2021-07-12
    python scripts/run_scoring_engine.py --hazard flood --date 2021-07-14
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

ALL_HAZARDS = ["flood", "wildfire", "heat_acute"]


def main():
    parser = argparse.ArgumentParser(description="Risk Scoring Engine")
    parser.add_argument("--hazard",   default="all",
                        help="Hazard type: flood | wildfire | heat_acute | all (default: all)")
    parser.add_argument("--date",     default=None,
                        help="ISO date to score, e.g. 2021-07-14 (default: yesterday)")
    parser.add_argument("--scenario", default="baseline",
                        help="NGFS scenario (default: baseline)")
    parser.add_argument("--horizon",  default="current",
                        help="Time horizon: current | 2030 | 2050 | 2100 (default: current)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Compute scores but do not write to canonical_scores")
    args = parser.parse_args()

    from ml.scoring.engine import run as score

    target_date = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    hazards = ALL_HAZARDS if args.hazard == "all" else [args.hazard]

    logger.info("=" * 60)
    logger.info("  Risk Scoring Engine")
    logger.info(f"  Date     : {target_date}")
    logger.info(f"  Hazards  : {hazards}")
    logger.info(f"  Scenario : {args.scenario}")
    logger.info(f"  Horizon  : {args.horizon}")
    logger.info(f"  Dry run  : {args.dry_run}")
    logger.info("=" * 60)

    total_cells = 0
    total_high  = 0
    total_compound = 0

    for hazard in hazards:
        logger.info(f"\n── {hazard.upper()} ──────────────────────")
        try:
            result = score(
                hazard_type=hazard,
                target_date=target_date,
                scenario=args.scenario,
                time_horizon=args.horizon,
                dry_run=args.dry_run,
            )
            total_cells    += result.n_cells_scored
            total_high     += result.n_high_risk
            total_compound += result.n_compound
            logger.info(
                f"  cells={result.n_cells_scored}  "
                f"high_risk={result.n_high_risk}  "
                f"compound={result.n_compound}  "
                f"model={result.model_version}  "
                f"{result.elapsed_seconds}s"
            )
        except Exception as exc:
            logger.error(f"  {hazard} scoring FAILED: {exc}", exc_info=True)

    logger.info("")
    logger.info(f"Scoring complete — {total_cells:,} cells  "
                f"{total_high:,} HIGH+  {total_compound} compound events")

    if not args.dry_run:
        logger.info("Next: check canonical_scores in Adminer (http://localhost:8080)")


if __name__ == "__main__":
    main()
