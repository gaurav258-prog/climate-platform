"""
Fetch real burn labels from NASA FIRMS (VIIRS active fire) for the wildfire events.

Replaces the hand-drawn burn bounding boxes with actual satellite fire detections:
a H3 cell is 'burned' if VIIRS saw fire in it (confidence != low) within the event
window. Far better labels for both training and honest evaluation.

Writes data/firms_burned_cells.json: {event_name: {"cells": [...h3...], "n": detections}}.
Uses VIIRS_SNPP_SP archive (2012-2026). Area API caps day range at 5, so we tile
three 5-day windows across peak-7 .. peak+8.
"""
import io
import csv
import json
import os
import sys
from datetime import timedelta

import h3
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_multievent_wildfire import EVENTS

from core.config import settings

OUT = "data/firms_burned_cells.json"
SRC = "VIIRS_SNPP_SP"
H3_RES = 8


def fetch_event(ev, key):
    n, w, s, e = ev["fetch_area"]          # stored [N, W, S, E]
    area = f"{w},{s},{e},{n}"              # FIRMS wants W,S,E,N
    cells, total = {}, 0
    for off in (-7, -2, 3):                # three 5-day windows → peak-7 .. peak+8
        start = (ev["peak"] + timedelta(days=off)).isoformat()
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{SRC}/{area}/5/{start}"
        r = requests.get(url, timeout=60)
        if not r.text or r.text.startswith("Invalid"):
            continue
        for row in csv.DictReader(io.StringIO(r.text)):
            if row.get("confidence", "n") == "l":   # drop low-confidence
                continue
            total += 1
            c = h3.latlng_to_cell(float(row["latitude"]), float(row["longitude"]), H3_RES)
            cells[c] = cells.get(c, 0) + 1
    return cells, total


def main():
    key = settings.FIRMS_API_KEY
    if not key:
        print("FIRMS_API_KEY not set"); sys.exit(1)
    out = {}
    for ev in EVENTS:
        cells, total = fetch_event(ev, key)
        out[ev["name"]] = {"cells": sorted(cells), "n": total}
        print(f"{ev['name']:30s} {total:5d} detections → {len(cells):4d} burned H3 cells")
    os.makedirs("data", exist_ok=True)
    json.dump(out, open(OUT, "w"))
    print(f"\nwrote {OUT}: {sum(len(v['cells']) for v in out.values())} burned cells across "
          f"{len(out)} events")


if __name__ == "__main__":
    main()
