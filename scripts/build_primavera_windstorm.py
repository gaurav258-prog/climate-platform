"""Build the European windstorm gust maps from the PRIMAVERA event set (the product owner's decisions of 2026-10-25):
each run's winters read from the published archives (scripts/fetch_primavera_windstorm.py), each winter's highest gust per
grid cell, and the return levels of the 1,332 winters — services.loss.windstorm_events.compact. Then, unless --no-sample,
the gust maps sampled at every asset location (services.loss.intensity.sample).

    venv/bin/python -m scripts.build_primavera_windstorm [--no-sample]
"""
from __future__ import annotations

import json
import logging
import sys


def main(sample: bool = True) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from services.loss import windstorm_events
    record = windstorm_events.compact()
    print(json.dumps({k: v for k, v in record.items() if k != "runs"}, indent=1))
    for run, c in record["runs"].items():
        print(f"  {run}: {c['footprints']} footprints, {c['winters']} winters, "
              f"{c['central_date_outside_oct_mar']} centred outside October–March, licence attribute "
              f"{[x[:60] for x in c['file_licence_attribute']]}")
    if sample:
        from core.db.session import get_session
        from services.loss.intensity import sample as sample_layer
        with get_session() as s:
            print(sample_layer(s, windstorm_events.LAYER))
    return 0


if __name__ == "__main__":
    sys.exit(main("--no-sample" not in sys.argv[1:]))
