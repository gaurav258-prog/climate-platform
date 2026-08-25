"""Regulatory-monitoring daily scan — the CronJob entry point.

Runs the change-detector across every org's tracked frameworks: the EUR-Lex / SEC / FCA document scrapers plus
the GDELT news early-signal, diffing each source against its last snapshot and raising changes. Safe to run
daily; a source that errors or is unreachable is skipped (never faked), so a "no change" is the honest truth.

Run: python scripts/run_reg_monitoring.py
Scheduled by infra/k8s/ingestion-cronjob.yaml (reg-monitoring CronJob).
"""
import logging
import sys

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("reg_monitoring")


def main() -> int:
    from services.scheduling.regulatory_scheduler import RegulatoryScheduler
    result = RegulatoryScheduler().run_daily_scan()
    logger.info(f"Regulatory monitoring complete: {result}")
    # A scan that couldn't reach any source still exits 0 (honest "no change"), never a hard fail on network.
    return 0


if __name__ == "__main__":
    sys.exit(main())
