"""Sample a hazard intensity layer at every asset location not yet held (E171). Usage:
    PYTHONPATH=. venv/bin/python -m scripts.sample_intensity [layer_key]   (default jrc_river_flood)"""
import logging
import sys

from services.loss.intensity import sample_job

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    print(sample_job(sys.argv[1] if len(sys.argv) > 1 else "jrc_river_flood"))
