"""Build the compact STORM v4 event set (E171) from the published files and record its checksums. Usage:
    PYTHONPATH=. venv/bin/python -m scripts.compact_storm_events"""
import logging

from services.loss.storm_events import compact

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    print(compact())
